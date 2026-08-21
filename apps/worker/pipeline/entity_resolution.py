"""기업명 ↔ corp_code 해소 (§3.2.1, Phase 1).

뉴스 텍스트의 표기 흔들림(정식명/약칭/영문명/티커)을 dim_company.aliases 로 흡수한다.
"""
from __future__ import annotations

import re

from ..core import db, get_logger

log = get_logger(__name__)

_SUFFIX_PATTERN = re.compile(
    r"(주식회사|\(주\)|㈜|Co\.,?\s*Ltd\.?|Corporation|Corp\.?|Inc\.?)", re.IGNORECASE
)
_STRIP_PATTERN = re.compile(r"[\s\-_.,]")

# 파일럿 기업 별칭 사전 (§5 Phase 1-1). 팀에서 확정한 나머지 파일럿 종목이 정해지면 이어서 채운다.
PILOT_ALIASES: dict[str, list[str]] = {
    "005930": ["삼성전자", "삼전", "Samsung Electronics"],
}


def normalize_name(name: str) -> str:
    """'(주)', '주식회사', 공백, 대소문자 등을 제거한 비교용 키."""
    if not name:
        return ""
    stripped = _SUFFIX_PATTERN.sub("", name)
    stripped = _STRIP_PATTERN.sub("", stripped)
    return stripped.strip().lower()


def resolve_by_name(name: str) -> str | None:
    """표기 -> corp_code. 정확일치 -> 별칭 -> 정규화 후 부분일치 순으로 시도."""
    if not name:
        return None
    query = name.strip()
    if not query:
        return None

    if query.isdigit() and len(query) == 6:
        row = db.fetch_one(
            "SELECT corp_code FROM dim_company WHERE stock_code = :code", {"code": query}
        )
        if row:
            return row["corp_code"]

    row = db.fetch_one(
        "SELECT corp_code FROM dim_company WHERE corp_name = :name", {"name": query}
    )
    if row:
        return row["corp_code"]

    row = db.fetch_one(
        "SELECT corp_code FROM dim_company WHERE :name = ANY(aliases)", {"name": query}
    )
    if row:
        return row["corp_code"]

    normalized_target = normalize_name(query)
    if not normalized_target:
        return None

    core = normalized_target[:4] if len(normalized_target) >= 4 else normalized_target
    candidates = db.fetch_all(
        """
        SELECT corp_code, corp_name, aliases
        FROM dim_company
        WHERE corp_name ILIKE :pattern
           OR EXISTS (SELECT 1 FROM unnest(aliases) AS alias WHERE alias ILIKE :pattern)
        """,
        {"pattern": f"%{core}%"},
    )
    for row in candidates:
        names_to_check = [row["corp_name"], *(row["aliases"] or [])]
        if any(normalize_name(n) == normalized_target for n in names_to_check):
            return row["corp_code"]

    return None


def search_companies(query: str, limit: int = 10) -> list[dict]:
    """프론트 검색창용 기업 조회 (이름/별칭/종목코드 부분일치)."""
    q = query.strip()
    if not q:
        return []

    pattern = f"%{q}%"
    return db.fetch_all(
        """
        SELECT DISTINCT corp_code, stock_code, corp_name, sector
        FROM dim_company
        WHERE corp_name ILIKE :pattern
           OR stock_code ILIKE :pattern
           OR EXISTS (SELECT 1 FROM unnest(aliases) AS alias WHERE alias ILIKE :pattern)
        ORDER BY corp_name
        LIMIT :limit
        """,
        {"pattern": pattern, "limit": limit},
    )


def upsert_aliases(stock_code: str, aliases: list[str]) -> int:
    """dim_company.aliases 갱신 (기존 값과 병합, 중복 제거)."""
    return db.execute(
        """
        UPDATE dim_company
        SET aliases = (
            SELECT array_agg(DISTINCT alias)
            FROM unnest(COALESCE(aliases, ARRAY[]::TEXT[]) || :new_aliases) AS alias
        )
        WHERE stock_code = :stock_code
        """,
        {"stock_code": stock_code, "new_aliases": aliases},
    )


def seed_pilot_aliases() -> int:
    """PILOT_ALIASES 를 dim_company 에 반영한다. Phase 1 완료 기준 점검용."""
    total = 0
    for stock_code, aliases in PILOT_ALIASES.items():
        total += upsert_aliases(stock_code, aliases)
    return total
