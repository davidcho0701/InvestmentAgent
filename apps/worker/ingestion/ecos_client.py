"""한국은행 ECOS 클라이언트 (Phase 3)."""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..core import db, get_logger, settings

log = get_logger(__name__)

BASE_URL = "https://ecos.bok.or.kr/api"

# 수집 대상 지표: (통계표코드, 항목코드, 주기, 내부 지표명)
INDICATORS: list[tuple[str, str, str, str]] = [
    ("722Y001", "0101000", "M", "base_rate"),        # 한국은행 기준금리
    ("817Y002", "010200000", "M", "ktb_3y"),         # 국고채 3년
    ("731Y001", "0000001", "M", "usd_krw"),          # 원/달러 환율
    ("901Y009", "0", "M", "cpi"),                    # 소비자물가지수
]

# 데이터가 없을 때(정상 케이스) ECOS 가 내려주는 코드
_NO_DATA_CODES = {"INFO-200"}

_retry_network = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)


class EcosApiError(RuntimeError):
    """ECOS 응답에 RESULT.CODE 가 존재(정상 데이터 없음 제외)하는 에러 케이스."""


def _lookback_period(cycle: str, lookback: int = 24) -> tuple[str, str]:
    """cycle(M=월,Q=분기,A=연) 기준 오늘부터 lookback 기간 전까지 (start, end) 문자열을 만든다."""
    from datetime import date

    today = date.today()
    if cycle == "M":
        end = f"{today.year}{today.month:02d}"
        total_months = today.year * 12 + (today.month - 1) - lookback
        start_year, start_month = divmod(total_months, 12)
        start = f"{start_year}{start_month + 1:02d}"
        return start, end
    if cycle == "Q":
        quarter = (today.month - 1) // 3 + 1
        end = f"{today.year}Q{quarter}"
        total_quarters = today.year * 4 + (quarter - 1) - lookback
        start_year, start_quarter = divmod(total_quarters, 4)
        start = f"{start_year}Q{start_quarter + 1}"
        return start, end
    if cycle == "A":
        return str(today.year - lookback), str(today.year)
    raise ValueError(f"지원하지 않는 주기: {cycle}")


@_retry_network
def fetch_indicator(
    stat_code: str, item_code: str, cycle: str, start: str, end: str
) -> list[dict[str, Any]]:
    """StatisticSearch 호출 -> [{period, value}]."""
    url = (
        f"{BASE_URL}/StatisticSearch/{settings.ecos_api_key}/json/kr/1/500/"
        f"{stat_code}/{cycle}/{start}/{end}/{item_code}"
    )
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        payload = resp.json()

    if "RESULT" in payload:
        code = payload["RESULT"].get("CODE")
        message = payload["RESULT"].get("MESSAGE")
        if code in _NO_DATA_CODES:
            return []
        raise EcosApiError(f"ECOS 조회 실패 ({code}): {message}")

    rows = payload.get("StatisticSearch", {}).get("row", [])
    points: list[dict[str, Any]] = []
    for row in rows:
        raw_value = row.get("DATA_VALUE")
        if raw_value in (None, ""):
            continue
        try:
            points.append({"period": row["TIME"], "value": float(raw_value)})
        except (KeyError, ValueError):
            log.warning("ECOS 값 파싱 실패", row=row)
    return points


def sync_all_indicators() -> int:
    """INDICATORS 전체를 fact_macro_indicator 에 upsert. 월 1회 배치."""
    total = 0
    for stat_code, item_code, cycle, indicator_name in INDICATORS:
        start, end = _lookback_period(cycle)
        try:
            points = fetch_indicator(stat_code, item_code, cycle, start, end)
        except Exception:
            log.exception("ECOS 지표 동기화 실패", indicator=indicator_name)
            continue
        if not points:
            continue

        rows = [
            {"indicator_code": indicator_name, "period": p["period"], "value": p["value"]}
            for p in points
        ]
        db.execute(
            """
            INSERT INTO fact_macro_indicator (indicator_code, period, value)
            VALUES (:indicator_code, :period, :value)
            ON CONFLICT (indicator_code, period) DO UPDATE SET value = EXCLUDED.value
            """,
            rows,
        )
        total += len(rows)
        log.info("ECOS 지표 동기화", indicator=indicator_name, count=len(rows))
    return total
