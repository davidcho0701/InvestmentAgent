"""거시경제 조정 스코어 (§3.2.5, Phase 3).

지표 변화량 × 업종 민감도 -> -1 ~ +1 범위의 macro_adjustment_score.
"""
from __future__ import annotations

from ..core import db, get_logger

log = get_logger(__name__)

# dim_sector_sensitivity 의 문자열 등급 -> 수치 계수
SENSITIVITY_WEIGHT = {"고": 1.0, "중": 0.5, "저": 0.2}


def sensitivity_coefficient(grade: str | None) -> float:
    return SENSITIVITY_WEIGHT.get(grade or "", 0.5)


def indicator_delta(indicator_code: str, periods: int = 3) -> float | None:
    """최근 N기 지표 변화율. fact_macro_indicator 조회."""
    rows = db.fetch_all(
        """
        SELECT value FROM fact_macro_indicator
        WHERE indicator_code = :indicator_code
        ORDER BY period DESC
        LIMIT :periods
        """,
        {"indicator_code": indicator_code, "periods": periods},
    )
    if len(rows) < periods:
        return None

    latest = rows[0]["value"]
    baseline = rows[-1]["value"]
    if latest is None or baseline in (None, 0):
        return None
    return (latest - baseline) / abs(baseline)


def compute_macro_adjustment(sector: str) -> float:
    """업종 기준 거시 조정 스코어(-1 ~ +1).

    금리 상승은 rate_sensitivity 가 높은 업종에 음(-), 환율 상승은 수출 업종에 양(+) 방향.
    두 요인의 가중합을 -1~+1 로 클램프한다. 회귀 기반 추정으로 대체 가능한 규칙 기반 초기값.
    """
    row = db.fetch_one(
        "SELECT rate_sensitivity, fx_sensitivity FROM dim_sector_sensitivity "
        "WHERE sector = :sector",
        {"sector": sector},
    )
    rate_grade = row["rate_sensitivity"] if row else None
    fx_grade = row["fx_sensitivity"] if row else None

    rate_delta = indicator_delta("base_rate")
    fx_delta = indicator_delta("usd_krw")

    rate_component = -sensitivity_coefficient(rate_grade) * (rate_delta or 0.0)
    fx_component = sensitivity_coefficient(fx_grade) * (fx_delta or 0.0)

    score = rate_component + fx_component
    return max(-1.0, min(1.0, score))
