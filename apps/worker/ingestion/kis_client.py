"""한국투자증권(KIS) 클라이언트 — 시세/투자의견 조회 전용 (Phase 3, 5).

제약(§7): 주문(order) 관련 엔드포인트는 이 코드베이스에 포함하지 않는다.
"""
from __future__ import annotations

from typing import Any

from ..core import get_logger, settings

log = get_logger(__name__)

REAL_BASE = "https://openapi.koreainvestment.com:9443"
MOCK_BASE = "https://openapivts.koreainvestment.com:29443"


def base_url() -> str:
    return MOCK_BASE if settings.kis_is_mock else REAL_BASE


def get_access_token() -> str:
    """OAuth 토큰 발급. 발급 제한이 있으므로 Redis 에 만료 전까지 캐시한다."""
    raise NotImplementedError("Phase 3")


def get_approval_key() -> str:
    """WebSocket 접속용 approval_key 발급."""
    raise NotImplementedError("Phase 5")


def fetch_analyst_consensus(stock_code: str) -> list[dict[str, Any]]:
    """종목투자의견 / 증권사별 투자의견 조회 -> fact_analyst_consensus 적재용 목록."""
    raise NotImplementedError("Phase 3")


def fetch_daily_ohlcv(stock_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """과거 일봉 OHLCV (스냅샷용, 무저장)."""
    raise NotImplementedError("Phase 5")
