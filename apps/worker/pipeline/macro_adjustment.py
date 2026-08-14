"""거시경제 조정 스코어 (§3.2.5, Phase 3).

지표 변화량 × 업종 민감도 -> -1 ~ +1 범위의 macro_adjustment_score.
"""
from __future__ import annotations

from ..core import get_logger

log = get_logger(__name__)

# dim_sector_sensitivity 의 문자열 등급 -> 수치 계수
SENSITIVITY_WEIGHT = {"고": 1.0, "중": 0.5, "저": 0.2}


def sensitivity_coefficient(grade: str | None) -> float:
    return SENSITIVITY_WEIGHT.get(grade or "", 0.5)


def indicator_delta(indicator_code: str, periods: int = 3) -> float | None:
    """최근 N기 지표 변화율. fact_macro_indicator 조회."""
    raise NotImplementedError("Phase 3")


def compute_macro_adjustment(sector: str) -> float:
    """업종 기준 거시 조정 스코어(-1 ~ +1).

    금리 상승은 rate_sensitivity 가 높은 업종에 음(-), 환율 상승은 수출 업종에 양(+) 방향.
    """
    raise NotImplementedError("Phase 3")
