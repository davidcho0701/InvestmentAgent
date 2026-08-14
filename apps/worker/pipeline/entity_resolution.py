"""기업명 ↔ corp_code 해소 (§3.2.1, Phase 1).

뉴스 텍스트의 표기 흔들림(정식명/약칭/영문명/티커)을 dim_company.aliases 로 흡수한다.
"""
from __future__ import annotations

from ..core import get_logger

log = get_logger(__name__)


def resolve_by_name(name: str) -> str | None:
    """표기 -> corp_code. 정확일치 -> 별칭 -> 정규화 후 부분일치 순으로 시도."""
    raise NotImplementedError("Phase 1")


def normalize_name(name: str) -> str:
    """'(주)', '주식회사', 공백, 대소문자 등을 제거한 비교용 키."""
    raise NotImplementedError("Phase 1")


def search_companies(query: str, limit: int = 10) -> list[dict]:
    """프론트 검색창용 기업 조회 (이름/별칭/종목코드 부분일치)."""
    raise NotImplementedError("Phase 1")
