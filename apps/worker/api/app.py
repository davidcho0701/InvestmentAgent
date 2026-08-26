"""Local visual monitor for the Milestone 1 KIS market-data connection."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from apps.worker.ingestion.kis_client import KISAPIError, KISClient, KISSettings, validate_stock_code
from apps.worker.pipeline.pattern_detection import annotate
from apps.worker.streaming.candle_aggregator import CandleAggregator, OHLCVCandle
from apps.worker.streaming.ws_consumer import DomesticExecutionTick, KISWebSocketConsumer

logger = logging.getLogger(__name__)
# Korea has no daylight-saving adjustment; using a fixed offset also works on
# Windows Python installations that do not ship IANA zoneinfo data.
KOREA_TIMEZONE = timezone(timedelta(hours=9), name="KST")
MAX_RECENT_TICKS = 30
MAX_CHART_CANDLES = 60
MAX_CHART_ANNOTATIONS = 20


@dataclass(frozen=True, slots=True)
class DashboardTick:
    stock_code: str
    executed_at: str
    price: str
    execution_volume: int
    accumulated_volume: int
    ask_price: str | None
    bid_price: str | None


class RecentTickStore:
    """A small in-memory view model; persistence belongs to a later milestone."""

    def __init__(self, max_items: int = MAX_RECENT_TICKS) -> None:
        self._ticks: deque[DashboardTick] = deque(maxlen=max_items)
        self._lock = asyncio.Lock()

    async def add(self, tick: DomesticExecutionTick) -> None:
        async with self._lock:
            self._ticks.appendleft(
                DashboardTick(
                    stock_code=tick.stock_code,
                    executed_at=_format_execution_time(tick),
                    price=_format_decimal(tick.price),
                    execution_volume=tick.execution_volume,
                    accumulated_volume=tick.accumulated_volume,
                    ask_price=_format_decimal(tick.ask_price),
                    bid_price=_format_decimal(tick.bid_price),
                )
            )

    async def snapshot(self) -> list[dict[str, str | int | None]]:
        async with self._lock:
            return [asdict(tick) for tick in self._ticks]


class ChartLiteracyStore:
    """Keep B-only candle history and neutral explanations in process memory.

    This intentionally has no database, cache, DART, or scoring dependency.
    """

    def __init__(self) -> None:
        self._candles: deque[OHLCVCandle] = deque(maxlen=MAX_CHART_CANDLES)
        self._annotations: deque[dict[str, Any]] = deque(maxlen=MAX_CHART_ANNOTATIONS)
        self._lock = asyncio.Lock()

    async def add_finalized_candle(self, candle: OHLCVCandle) -> None:
        async with self._lock:
            self._candles.append(candle)
            rows = [_pattern_row(item) for item in self._candles]
            detected = annotate(candle.stock_code, rows)
            current_annotations = [
                _annotation_payload(item)
                for item in detected
                if item["ts"] == candle.timestamp
            ]
            self._annotations.extend(current_annotations)

    async def snapshot(self) -> tuple[list[dict[str, str | int | None]], list[dict[str, Any]]]:
        async with self._lock:
            return (
                [candle.as_dict() for candle in self._candles],
                list(self._annotations),
            )


@dataclass(slots=True)
class DashboardServices:
    client: KISClient
    consumer: KISWebSocketConsumer
    ticks: RecentTickStore
    candles: CandleAggregator
    literacy: ChartLiteracyStore
    stock_code: str


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = KISSettings.from_env()
        stock_code = validate_stock_code(_configured_stock_code())
        client = KISClient(settings)
        tick_store = RecentTickStore()
        literacy_store = ChartLiteracyStore()
        candle_aggregator = CandleAggregator(on_candle_finalized=literacy_store.add_finalized_candle)

        async def process_tick(tick: DomesticExecutionTick) -> None:
            await tick_store.add(tick)
            await candle_aggregator.ingest(tick)

        consumer = KISWebSocketConsumer(
            settings,
            approval_key_provider=client.get_websocket_approval_key,
            on_tick=process_tick,
        )
        await consumer.subscribe(stock_code)
        consumer.start()
        app.state.services = DashboardServices(
            client=client,
            consumer=consumer,
            ticks=tick_store,
            candles=candle_aggregator,
            literacy=literacy_store,
            stock_code=stock_code,
        )
        logger.info("InvestScope dashboard started for %s", stock_code)
        try:
            yield
        finally:
            await consumer.close()
            await candle_aggregator.flush()
            await client.aclose()
            logger.info("InvestScope dashboard stopped")

    app = FastAPI(title="InvestScope Live Monitor", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return render_dashboard()

    @app.get("/api/dashboard")
    async def dashboard_data(request: Request) -> dict[str, object]:
        services = _services(request)
        finalized, annotations = await services.literacy.snapshot()
        candles_by_timestamp = {candle["timestamp"]: candle for candle in finalized}
        for candle in await services.candles.current_candles():
            candles_by_timestamp[candle.timestamp.isoformat()] = candle.as_dict()
        return {
            "stock_code": services.stock_code,
            "connected": services.consumer.is_connected,
            "running": services.consumer.is_running,
            "last_disconnect_kind": services.consumer.last_disconnect_kind,
            "last_close_code": services.consumer.last_close_code,
            "subscriptions": list(await services.consumer.get_subscriptions()),
            "last_ticks": await services.ticks.snapshot(),
            "candles": list(candles_by_timestamp.values())[-MAX_CHART_CANDLES:],
            "annotations": annotations,
            "updated_at": datetime.now(KOREA_TIMEZONE).isoformat(),
        }

    @app.get("/api/current-price/{stock_code}")
    async def current_price(stock_code: str, request: Request) -> dict[str, object]:
        services = _services(request)
        try:
            code = validate_stock_code(stock_code)
            price = await services.client.get_current_price(code)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except KISAPIError as error:
            raise HTTPException(status_code=502, detail="KIS current-price request failed") from error

        return {
            "stock_code": code,
            "price": price.get("stck_prpr"),
            "change": price.get("prdy_vrss"),
            "change_rate": price.get("prdy_ctrt"),
            "volume": price.get("acml_vol"),
            "as_of": datetime.now(KOREA_TIMEZONE).isoformat(),
        }

    @app.post("/api/reconnect")
    async def reconnect(request: Request) -> dict[str, bool]:
        await _services(request).consumer.reconnect()
        return {"accepted": True}

    return app


def _services(request: Request) -> DashboardServices:
    services = getattr(request.app.state, "services", None)
    if not isinstance(services, DashboardServices):
        raise HTTPException(status_code=503, detail="Dashboard is starting")
    return services


def _configured_stock_code() -> str:
    # KISSettings.from_env already loaded .env before the application lifespan starts.
    import os

    return os.getenv("KIS_TEST_STOCK_CODE", "005930")


def _format_execution_time(tick: DomesticExecutionTick) -> str:
    if len(tick.execution_time) == 6 and len(tick.business_date) == 8:
        return (
            f"{tick.business_date[0:4]}-{tick.business_date[4:6]}-{tick.business_date[6:8]} "
            f"{tick.execution_time[0:2]}:{tick.execution_time[2:4]}:{tick.execution_time[4:6]}"
        )
    return tick.execution_time


def _format_decimal(value: object) -> str | None:
    if value is None:
        return None
    return f"{value:,}"


def _pattern_row(candle: OHLCVCandle) -> dict[str, object]:
    return {
        "ts": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _annotation_payload(annotation: dict[str, Any]) -> dict[str, Any]:
    timestamp = annotation["ts"]
    if not isinstance(timestamp, datetime):
        raise TypeError("Pattern annotation timestamp must be a datetime")
    return {
        "timestamp": timestamp.isoformat(),
        "pattern_label": annotation["pattern_label"],
        "indicator_flags": annotation["indicator_flags"],
        "explanation_text": annotation["explanation_text"],
    }


def _legacy_render_dashboard() -> str:
    """Return a dependency-free local dashboard so the monitor works offline."""

    return """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InvestScope · Live Monitor</title>
  <style>
    :root { color-scheme: dark; --bg:#07111f; --card:#0d1b2f; --line:#20324c; --text:#e9f1ff; --muted:#8ca0bc; --mint:#57e4c2; --blue:#7aa9ff; --red:#ff7f91; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font:15px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color:var(--text); background:radial-gradient(circle at 14% 0%, #14345b 0, transparent 34rem), radial-gradient(circle at 90% 18%, #12342f 0, transparent 30rem), var(--bg); }
    main { max-width:1120px; margin:0 auto; padding:52px 24px 72px; }
    header { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; margin-bottom:32px; }
    .eyebrow { color:var(--mint); letter-spacing:.14em; font-size:11px; font-weight:800; text-transform:uppercase; }
    h1 { margin:6px 0 0; font-size:clamp(31px,5vw,52px); line-height:1.05; letter-spacing:-.045em; }
    .subtitle { color:var(--muted); margin:12px 0 0; max-width:630px; }
    .pill { display:inline-flex; align-items:center; gap:8px; border:1px solid var(--line); border-radius:99px; padding:9px 13px; background:#0a1729cc; font-size:13px; white-space:nowrap; }
    .dot { width:8px; height:8px; border-radius:50%; background:var(--red); box-shadow:0 0 0 4px #ff7f9122; }
    .dot.live { background:var(--mint); box-shadow:0 0 0 4px #57e4c222; }
    .grid { display:grid; grid-template-columns:1.15fr .85fr; gap:16px; }
    .card { background:linear-gradient(145deg,#10213aeb,#0b1729e8); border:1px solid var(--line); border-radius:18px; padding:22px; box-shadow:0 24px 56px #00000028; }
    .label { color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
    .price { margin:8px 0 4px; font-size:42px; font-weight:800; letter-spacing:-.045em; }
    .meta { color:var(--muted); font-size:13px; }
    .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:22px; }
    .stat { padding:12px; background:#091526a8; border:1px solid #1c2b42; border-radius:12px; }
    .stat b { display:block; margin-top:4px; font-size:16px; }
    .candle-preview { margin-top:18px; padding:15px; border:1px solid #1c3d56; border-radius:12px; background:linear-gradient(130deg,#0b2332,#0b192b); }
    .candle-values { display:block; margin:6px 0; color:var(--mint); font-size:17px; font-weight:800; letter-spacing:-.02em; }
    button { border:1px solid #325787; background:#16365d; color:var(--text); border-radius:10px; padding:10px 13px; font:inherit; cursor:pointer; }
    button:hover { background:#1c477a; } .actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:20px; }
    .stream { margin-top:16px; } .stream .card { padding:0; overflow:hidden; }
    .stream-head { padding:20px 22px; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--line); }
    table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; } th,td { padding:13px 22px; text-align:left; border-bottom:1px solid #18283e; } th { color:var(--muted); font-size:11px; letter-spacing:.06em; text-transform:uppercase; } td.price-cell { color:var(--mint); font-weight:750; } tr:last-child td { border-bottom:0; }
    .empty { padding:44px 22px; color:var(--muted); text-align:center; } .footnote { margin:16px 2px 0; color:var(--muted); font-size:12px; }
    @media (max-width:720px) { main { padding:32px 16px; } header { display:block; } .pill { margin-top:18px; } .grid { grid-template-columns:1fr; } .stats { grid-template-columns:1fr; } th,td { padding:12px; } th:nth-child(4),td:nth-child(4) { display:none; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div><div class="eyebrow">KIS Developers · Milestone 1</div><h1>InvestScope<br>Live Monitor</h1><p class="subtitle">현재가와 실시간 체결 수신 상태를 한 화면에서 확인합니다. 이 화면은 투자 권유나 예측을 제공하지 않습니다.</p></div>
      <div class="pill"><span id="connection-dot" class="dot"></span><span id="connection-text">연결 확인 중</span></div>
    </header>
    <section class="grid">
      <article class="card"><div class="label"><span id="stock-code">005930</span> · 현재가</div><div id="current-price" class="price">—</div><div id="price-as-of" class="meta">KIS REST 조회 대기</div><div class="stats"><div class="stat"><div class="label">전일 대비</div><b id="change">—</b></div><div class="stat"><div class="label">등락률</div><b id="change-rate">—</b></div><div class="stat"><div class="label">누적 거래량</div><b id="volume">—</b></div></div><div class="actions"><button id="refresh-price">현재가 새로고침</button><button id="reconnect">WebSocket 재연결</button></div></article>
      <aside class="card"><div class="label">수신 상태</div><div id="stream-state" style="font-size:24px;font-weight:800;margin:8px 0">시작 중</div><p id="subscription" class="meta">구독 종목 확인 중</p><div class="candle-preview"><div class="label">현재 1분봉</div><div id="candle-time" class="meta">체결 수신 대기</div><strong id="candle-values" class="candle-values">—</strong><div id="candle-volume" class="meta">거래량 —</div></div><p class="meta">정규장 외에는 체결 데이터가 없을 수 있습니다. 수신 프레임은 메모리에 최근 30건만 표시합니다.</p></aside>
    </section>
    <section class="stream"><article class="card"><div class="stream-head"><div><div class="label">실시간 체결</div><strong>최근 수신 데이터</strong></div><span id="last-update" class="meta">—</span></div><div style="overflow:auto"><table><thead><tr><th>체결 시각</th><th>현재가</th><th>체결량</th><th>누적 거래량</th><th>매도 / 매수 호가</th></tr></thead><tbody id="tick-body"><tr><td class="empty" colspan="5">아직 수신된 체결이 없습니다.</td></tr></tbody></table></div></article></section>
    <p id="error" class="footnote">로컬 주소에서만 실행하세요: http://127.0.0.1:8000</p>
  </main>
  <script>
    const money = value => value == null || value === '' ? '—' : Number(value).toLocaleString('ko-KR');
    const text = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    let stockCode = '005930';
    async function requestJson(url, options) { const r = await fetch(url, options); if (!r.ok) throw new Error((await r.json()).detail || '요청에 실패했습니다.'); return r.json(); }
    async function refreshDashboard() { try { const data = await requestJson('/api/dashboard'); stockCode = data.stock_code; document.querySelector('#stock-code').textContent = stockCode; document.querySelector('#connection-dot').className = 'dot' + (data.connected ? ' live' : ''); document.querySelector('#connection-text').textContent = data.connected ? '실시간 연결됨' : (data.running ? '재연결 대기 중' : '연결 중지됨'); document.querySelector('#stream-state').textContent = data.connected ? 'LIVE · 수신 중' : '연결 대기'; const disconnect = data.last_disconnect_kind ? ' · 최근 상태: ' + data.last_disconnect_kind + (data.last_close_code ? ' (' + data.last_close_code + ')' : '') : ''; document.querySelector('#subscription').textContent = '구독 종목: ' + (data.subscriptions.join(', ') || '없음') + disconnect; const candle = data.open_candles.find(c => c.stock_code === stockCode); document.querySelector('#candle-time').textContent = candle ? candle.timestamp.slice(11, 16) + ' 기준' : '체결 수신 대기'; document.querySelector('#candle-values').textContent = candle ? `O ${money(candle.open)} · H ${money(candle.high)} · L ${money(candle.low)} · C ${money(candle.close)}` : '—'; document.querySelector('#candle-volume').textContent = candle ? '거래량 ' + money(candle.volume) : '거래량 —'; document.querySelector('#last-update').textContent = '갱신 ' + new Date(data.updated_at).toLocaleTimeString('ko-KR'); const rows = data.last_ticks.map(t => `<tr><td>${text(t.executed_at)}</td><td class="price-cell">${text(t.price)}원</td><td>${money(t.execution_volume)}</td><td>${money(t.accumulated_volume)}</td><td>${text(t.ask_price)} / ${text(t.bid_price)}</td></tr>`).join(''); document.querySelector('#tick-body').innerHTML = rows || '<tr><td class="empty" colspan="5">아직 수신된 체결이 없습니다. 장중에 자동으로 표시됩니다.</td></tr>'; document.querySelector('#error').textContent = '로컬 주소에서만 실행하세요: http://127.0.0.1:8000'; } catch (error) { document.querySelector('#error').textContent = '상태 조회 오류: ' + error.message; } }
    async function refreshPrice() { try { const data = await requestJson('/api/current-price/' + stockCode); document.querySelector('#current-price').textContent = money(data.price) + '원'; document.querySelector('#change').textContent = money(data.change) + '원'; document.querySelector('#change-rate').textContent = (data.change_rate ?? '—') + '%'; document.querySelector('#volume').textContent = money(data.volume); document.querySelector('#price-as-of').textContent = 'KIS REST · ' + new Date(data.as_of).toLocaleTimeString('ko-KR'); } catch (error) { document.querySelector('#price-as-of').textContent = '현재가 조회 오류: ' + error.message; } }
    document.querySelector('#refresh-price').addEventListener('click', refreshPrice); document.querySelector('#reconnect').addEventListener('click', async () => { try { await requestJson('/api/reconnect', {method:'POST'}); } catch (error) { document.querySelector('#error').textContent = '재연결 요청 오류: ' + error.message; } });
    refreshDashboard(); refreshPrice(); setInterval(refreshDashboard, 2000); setInterval(refreshPrice, 10000);
  </script>
</body>
</html>"""


def render_dashboard() -> str:
    """Dependency-free B-only monitor: KIS ticks, one-minute candles, explanations."""

    return """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InvestScope · Chart Literacy</title>
  <style>
    :root { color-scheme:dark; --bg:#07111f; --card:#10213a; --line:#263d5b; --text:#e8f0fc; --muted:#97a9c1; --mint:#5ee5c3; --amber:#f7c35a; --red:#ff8b9b; }
    * { box-sizing:border-box; } body { margin:0; background:radial-gradient(circle at 10% 0,#193b66,transparent 38rem),var(--bg); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
    main { max-width:1080px; margin:0 auto; padding:42px 20px 64px; } header { display:flex; justify-content:space-between; gap:16px; align-items:start; margin-bottom:24px; } h1 { margin:4px 0; font-size:clamp(30px,5vw,48px); letter-spacing:-.05em; } h2 { margin:0; font-size:17px; } .eyebrow,.label { color:var(--mint); font-size:11px; font-weight:800; letter-spacing:.1em; text-transform:uppercase; } .subtitle,.muted { color:var(--muted); } .pill { border:1px solid var(--line); border-radius:99px; padding:8px 12px; font-size:13px; white-space:nowrap; } .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--red); margin-right:6px; } .dot.live { background:var(--mint); box-shadow:0 0 0 4px #5ee5c322; }
    .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; } .card { background:linear-gradient(145deg,#122541ef,#0d1a2ce8); border:1px solid var(--line); border-radius:16px; padding:18px; box-shadow:0 18px 45px #0004; } .value { margin-top:7px; font-size:27px; font-weight:800; letter-spacing:-.04em; } .wide { grid-column:span 2; } .price-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin-top:13px; } .stat { background:#091627b8; border:1px solid #1d324b; border-radius:10px; padding:9px; } .stat b { display:block; margin-top:3px; font-size:16px; }
    .section { margin-top:16px; } .section-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:9px; } .insights { display:grid; gap:9px; } .insight { border-left:3px solid var(--amber); background:#2d251530; padding:12px 14px; border-radius:0 10px 10px 0; } .insight strong { color:#ffe1a2; } .insight p { margin:5px 0 0; color:#d4dfed; } table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; } th,td { border-bottom:1px solid #1e3149; padding:10px; text-align:left; } th { color:var(--muted); font-size:11px; } .scroll { overflow:auto; } details { margin-top:12px; border:1px solid var(--line); border-radius:10px; padding:12px; color:#cbd7e7; } summary { cursor:pointer; font-weight:700; color:var(--text); } dl { display:grid; gap:10px; margin:12px 0 0; } dt { color:var(--mint); font-weight:700; } dd { margin:1px 0 0; color:var(--muted); } .notice { margin-top:16px; color:var(--muted); font-size:12px; }
    @media (max-width:760px) { header { display:block; }.pill { display:inline-block; margin-top:12px; }.grid { grid-template-columns:1fr; }.wide { grid-column:auto; }.price-grid { grid-template-columns:repeat(2,1fr); } }
  </style>
</head>
<body><main>
  <header><div><div class="eyebrow">KIS Developers · Part 2</div><h1>차트 쉽게 읽기</h1><p class="subtitle">실시간 체결을 1분봉으로 묶고, 수치와 패턴을 쉬운 말로 설명합니다.</p></div><div class="pill"><span id="dot" class="dot"></span><span id="status">연결 확인 중</span></div></header>
  <section class="grid">
    <article class="card"><div class="label">현재가 · <span id="stock">005930</span></div><div id="price" class="value">—</div><div id="price-info" class="muted">KIS REST 조회 대기</div></article>
    <article class="card wide"><div class="label">현재 1분봉 OHLCV</div><div id="candle-time" class="muted">체결 수신 대기</div><div class="price-grid"><div class="stat">시가<b id="open">—</b></div><div class="stat">고가<b id="high">—</b></div><div class="stat">저가<b id="low">—</b></div><div class="stat">종가<b id="close">—</b></div><div class="stat">거래량<b id="volume">—</b></div></div></article>
  </section>
  <section class="section card"><div class="section-head"><div><div class="label">패턴 해설</div><h2>방금 감지된 차트 상태</h2></div><span id="candle-count" class="muted"></span></div><div id="insights" class="insights"><p class="muted">1분봉이 마감된 뒤 패턴이 감지되면 여기에 쉬운 설명이 표시됩니다.</p></div></section>
  <section class="section card"><div class="section-head"><div><div class="label">최근 1분봉</div><h2>OHLCV</h2></div><span id="updated" class="muted"></span></div><div class="scroll"><table><thead><tr><th>시각</th><th>시가</th><th>고가</th><th>저가</th><th>종가</th><th>거래량</th></tr></thead><tbody id="candles"><tr><td colspan="6" class="muted">캔들 수신 대기</td></tr></tbody></table></div></section>
  <details><summary>용어 사전</summary><dl><div><dt>봉(캔들)</dt><dd>1분 동안의 시가·고가·저가·종가를 한 묶음으로 보여줍니다.</dd></div><div><dt>거래량</dt><dd>해당 분에 실제 체결된 수량입니다. 가격 방향을 뜻하는 수치는 아닙니다.</dd></div><div><dt>이동평균선</dt><dd>여러 봉의 종가 평균입니다. 최근 가격 흐름을 비교하는 보조 정보입니다.</dd></div><div><dt>RSI(14)</dt><dd>최근 14개 구간의 가격 변화 강도를 0~100으로 표현한 지표입니다.</dd></div></dl></details>
  <p class="notice">이 화면의 모든 해설은 차트 수치 이해를 위한 정보이며, 매수·매도 투자 권유 또는 향후 가격 방향을 보장하는 투자 신호가 아닙니다.</p>
</main>
<script>
  const money = value => value == null || value === '' ? '—' : Number(value).toLocaleString('ko-KR');
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let stockCode = '005930';
  async function getJson(url) { const response = await fetch(url); if (!response.ok) throw new Error('요청에 실패했습니다.'); return response.json(); }
  async function refresh() {
    try {
      const data = await getJson('/api/dashboard'); stockCode = data.stock_code;
      document.querySelector('#stock').textContent = stockCode;
      document.querySelector('#dot').className = 'dot' + (data.connected ? ' live' : '');
      document.querySelector('#status').textContent = data.connected ? '실시간 연결됨' : (data.running ? '재연결 대기' : '연결 중');
      const candles = data.candles || []; const latest = candles.at(-1);
      document.querySelector('#candle-count').textContent = candles.length + '개 캔들';
      if (latest) { document.querySelector('#candle-time').textContent = latest.timestamp.slice(11,16) + ' 기준'; ['open','high','low','close','volume'].forEach(key => document.querySelector('#' + key).textContent = money(latest[key])); }
      document.querySelector('#candles').innerHTML = candles.slice(-10).reverse().map(c => `<tr><td>${escapeHtml(c.timestamp.slice(11,16))}</td><td>${money(c.open)}</td><td>${money(c.high)}</td><td>${money(c.low)}</td><td>${money(c.close)}</td><td>${money(c.volume)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">캔들 수신 대기</td></tr>';
      const annotations = data.annotations || [];
      document.querySelector('#insights').innerHTML = annotations.slice(-3).reverse().map(item => `<article class="insight"><strong>${escapeHtml(item.pattern_label)}</strong><p>${escapeHtml(item.explanation_text)}</p></article>`).join('') || '<p class="muted">1분봉이 마감된 뒤 패턴이 감지되면 여기에 쉬운 설명이 표시됩니다.</p>';
      document.querySelector('#updated').textContent = '갱신 ' + new Date(data.updated_at).toLocaleTimeString('ko-KR');
    } catch (error) { document.querySelector('#status').textContent = '서버 확인 필요'; }
  }
  async function refreshPrice() { try { const data = await getJson('/api/current-price/' + stockCode); document.querySelector('#price').textContent = money(data.price) + '원'; document.querySelector('#price-info').textContent = '전일 대비 ' + money(data.change) + '원 · ' + (data.change_rate ?? '—') + '%'; } catch (error) { document.querySelector('#price-info').textContent = '현재가 조회 대기'; } }
  refresh(); refreshPrice(); setInterval(refresh, 2000); setInterval(refreshPrice, 10000);
</script></body></html>"""


app = create_app()
