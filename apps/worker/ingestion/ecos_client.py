"""한국은행 ECOS 클라이언트 (Phase 3)."""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)

BASE_URL = "https://ecos.bok.or.kr/api"

# 수집 대상 지표: (통계표코드, 항목코드, 주기, 내부 지표명)
INDICATORS: list[tuple[str, str, str, str]] = [
    ("722Y001", "0101000", "M", "base_rate"),        # 한국은행 기준금리
    ("817Y002", "010200000", "M", "ktb_3y"),         # 국고채 3년
    ("731Y001", "0000001", "M", "usd_krw"),          # 원/달러 환율
    ("901Y009", "0", "M", "cpi"),                    # 소비자물가지수
]


def fetch_indicator(
    stat_code: str, item_code: str, cycle: str, start: str, end: str
) -> list[dict[str, Any]]:
    """StatisticSearch 호출 -> [{period, value}]."""
    raise NotImplementedError("Phase 3")


def sync_all_indicators() -> int:
    """INDICATORS 전체를 fact_macro_indicator 에 upsert. 월 1회 배치."""
    raise NotImplementedError("Phase 3")
