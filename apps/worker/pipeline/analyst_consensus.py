"""애널리스트 컨센서스 집계 (§3.2.7, Phase 3).

제약(§7): 이 값은 final_score 연산에 절대 섞지 않고, 별도 패널로만 노출한다.
"""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)


def sync_consensus(stock_code: str) -> int:
    """KIS 투자의견 조회 -> fact_analyst_consensus 적재."""
    raise NotImplementedError("Phase 3")


def summarize_consensus(stock_code: str, days: int = 90) -> dict[str, Any]:
    """최근 N일 의견 분포 + 평균 목표주가 요약 (프론트 패널용)."""
    raise NotImplementedError("Phase 3")
