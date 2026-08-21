"""한국투자증권(KIS) 클라이언트 — 시세/투자의견 조회 전용 (Phase 3, 5).

제약(§7): 주문(order) 관련 엔드포인트는 이 코드베이스에 포함하지 않는다.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..core import cache, get_logger, settings

log = get_logger(__name__)

REAL_BASE = "https://openapi.koreainvestment.com:9443"
MOCK_BASE = "https://openapivts.koreainvestment.com:29443"

_TOKEN_CACHE_KEY = "kis:access_token"

# ⚠️ 미검증: 종목투자의견 tr_id/응답 필드명은 실제 계정으로 1회 호출해 확인 후 고정할 것
# (KIS_APP_SECRET 미보유로 이번 세션에서 라이브 검증 못함). 담당 B 와 확인 후 조정 바람.
INVEST_OPINION_TR_ID = "FHKST663300C0"


class KisApiError(RuntimeError):
    """KIS 응답 rt_cd != '0'."""


def base_url() -> str:
    return MOCK_BASE if settings.kis_is_mock else REAL_BASE


def get_access_token() -> str:
    """OAuth 토큰 발급. 발급 제한이 있으므로 Redis 에 만료 전까지 캐시한다."""
    cached = cache.get_json(_TOKEN_CACHE_KEY)
    if cached and cached.get("token"):
        return cached["token"]

    with httpx.Client(base_url=base_url(), timeout=15.0) as client:
        resp = client.post(
            "/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": settings.kis_app_key,
                "appsecret": settings.kis_app_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()

    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 86400))
    # 만료 5분 전에는 캐시를 비워 재발급받도록 여유를 둔다.
    cache.set_json(_TOKEN_CACHE_KEY, {"token": token}, ttl_seconds=max(60, expires_in - 300))
    return token


def get_approval_key() -> str:
    """WebSocket 접속용 approval_key 발급."""
    raise NotImplementedError("Phase 5")


def _headers(tr_id: str) -> dict[str, str]:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {get_access_token()}",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
        "tr_id": tr_id,
        "custtype": "P",
    }


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def fetch_analyst_consensus(stock_code: str) -> list[dict[str, Any]]:
    """종목투자의견 / 증권사별 투자의견 조회 -> fact_analyst_consensus 적재용 목록.

    ⚠️ tr_id/응답 필드명 미검증 — KIS_APP_SECRET 확보 후 실제 응답으로 재확인 필요.
    """
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": "",
        "FID_INPUT_DATE_2": "",
    }
    with httpx.Client(base_url=base_url(), timeout=15.0) as client:
        resp = client.get(
            "/uapi/domestic-stock/v1/quotations/invest-opinion",
            params=params,
            headers=_headers(INVEST_OPINION_TR_ID),
        )
        resp.raise_for_status()
        payload = resp.json()

    if payload.get("rt_cd") != "0":
        raise KisApiError(f"투자의견 조회 실패: {payload.get('msg1')}")

    rows = payload.get("output", [])
    return [
        {
            "stock_code": stock_code,
            "report_date": row.get("stck_bsop_date"),
            "securities_firm": row.get("mbcr_name"),
            "opinion": row.get("invt_opnn"),
            "target_price": _to_float(row.get("hts_goal_prc")),
        }
        for row in rows
    ]


def fetch_daily_ohlcv(stock_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """과거 일봉 OHLCV (스냅샷용, 무저장)."""
    raise NotImplementedError("Phase 5")
