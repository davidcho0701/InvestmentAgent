"""차트 데이터 + 패턴 해설 (Phase 5).

제약: 해설은 어떤 경우에도 매수/매도 권유를 포함하지 않는다. 중립 어미 + "신호 아님" 문구 필수.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from ..core import db, get_logger
from ..ingestion.kis_client import validate_stock_code
from ..streaming.chart_runtime import RealtimeChartRuntime

router = APIRouter(prefix="/api/chart", tags=["chart"])
log = get_logger(__name__)

DISCLAIMER = "본 해설은 차트 형태에 대한 설명이며, 매매 신호가 아닙니다."


@router.get("/{stock_code}")
async def get_chart(
    stock_code: str,
    request: Request,
    user_id: str = Query(...),
    interval: str = "1m",
) -> dict:
    """Return live in-memory candles for watchlist symbols, else an explicit snapshot shell."""

    if interval != "1m":
        raise HTTPException(status_code=422, detail="현재는 1m interval만 지원합니다.")
    try:
        code = validate_stock_code(stock_code)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    runtime = _runtime(request)
    if _is_watchlisted(user_id, code):
        return {
            "mode": "realtime",
            "stock_code": code,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "candles": await runtime.chart_candles(code),
            "annotations": await runtime.chart_annotations(code),
        }

    # Historical KIS schema is intentionally not guessed.  Return a clearly
    # labelled empty snapshot until the verified historical client is added.
    return {
        "mode": "static",
        "stock_code": code,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "candles": [],
        "annotations": [],
    }


@router.websocket("/ws/{stock_code}")
async def chart_ws(websocket: WebSocket, stock_code: str) -> None:
    """Push current-minute candles from one backend KIS connection to browsers."""

    try:
        code = validate_stock_code(stock_code)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid stock code")
        return
    runtime = getattr(websocket.app.state, "chart_runtime", None)
    if not isinstance(runtime, RealtimeChartRuntime) or not await runtime.is_subscribed(code):
        await websocket.close(code=1008, reason="Realtime chart is unavailable for this symbol")
        return

    await websocket.accept()
    queue = await runtime.add_listener(code)
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.remove_listener(code, queue)


def _runtime(request: Request) -> RealtimeChartRuntime:
    runtime = getattr(request.app.state, "chart_runtime", None)
    if not isinstance(runtime, RealtimeChartRuntime):
        raise HTTPException(status_code=503, detail="실시간 차트 서비스가 준비되지 않았습니다.")
    return runtime


def _is_watchlisted(user_id: str, stock_code: str) -> bool:
    try:
        row = db.fetch_one(
            """
            SELECT 1
            FROM user_watchlist w
            JOIN dim_company c ON c.corp_code = w.corp_code
            WHERE w.user_id = :user_id AND c.stock_code = :stock_code
            """,
            {"user_id": user_id, "stock_code": stock_code},
        )
        return row is not None
    except Exception:
        log.warning("관심종목 조회 실패", stock_code=stock_code, exc_info=True)
        return False
