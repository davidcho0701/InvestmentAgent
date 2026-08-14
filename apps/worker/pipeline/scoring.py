"""final_score 계산 (§3.2.6). 가중치/정규화 파라미터는 config.yaml 에서 읽는다.

주의: 애널리스트 컨센서스는 final_score 에 절대 섞지 않는다 (§7).
"""
from __future__ import annotations

from typing import Any

from ..core.config import get_scoring_config


def normalize_to_score(value: float | None, min_val: float, max_val: float) -> float:
    """임의 범위 값을 0~100 으로 클램프 정규화. 결측은 중립값 50."""
    if value is None:
        return 50.0
    if max_val == min_val:
        return 50.0
    return max(0.0, min(100.0, (value - min_val) / (max_val - min_val) * 100))


def accrual_penalty(accrual_ratio: float | None) -> float:
    """발생액 비율이 임계치를 넘는 만큼 financial_health 에서 차감할 점수."""
    cfg = get_scoring_config()["accrual_penalty"]
    if accrual_ratio is None or accrual_ratio <= cfg["threshold"]:
        return 0.0
    excess = accrual_ratio - cfg["threshold"]
    return min(cfg["max_penalty"], excess * cfg["scale"])


def recommendation_label(final_score: float) -> str:
    for band in get_scoring_config()["recommendation_labels"]:
        if final_score >= band["min"]:
            return band["label"]
    return "중립"


def calculate_final_score(features: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """피처 dict -> (final_score, contributing_factors).

    features 기대 키:
      sector_percentile_rank, accrual_ratio, yoy_growth,
      news_sentiment_rolling_30d, macro_context
    """
    cfg = get_scoring_config()
    weights = cfg["weights"]
    norm = cfg["normalization"]

    penalty = accrual_penalty(features.get("accrual_ratio"))
    financial_health = max(
        0.0,
        normalize_to_score(
            features.get("sector_percentile_rank"),
            norm["financial_health"]["min"],
            norm["financial_health"]["max"],
        )
        - penalty,
    )
    financial_growth = normalize_to_score(
        features.get("yoy_growth"),
        norm["financial_growth"]["min"],
        norm["financial_growth"]["max"],
    )
    news_sentiment = normalize_to_score(
        features.get("news_sentiment_rolling_30d"),
        norm["news_sentiment"]["min"],
        norm["news_sentiment"]["max"],
    )
    macro_adjustment = normalize_to_score(
        features.get("macro_context"),
        norm["macro_adjustment"]["min"],
        norm["macro_adjustment"]["max"],
    )

    final_score = (
        weights["financial_health"] * financial_health
        + weights["financial_growth"] * financial_growth
        + weights["news_sentiment"] * news_sentiment
        + weights["macro_adjustment"] * macro_adjustment
    )

    contributing_factors = {
        "financial_health": {
            "score": round(financial_health, 2),
            "weight": weights["financial_health"],
            "raw": features.get("sector_percentile_rank"),
            "accrual_penalty": round(penalty, 2),
        },
        "financial_growth": {
            "score": round(financial_growth, 2),
            "weight": weights["financial_growth"],
            "raw": features.get("yoy_growth"),
        },
        "news_sentiment": {
            "score": round(news_sentiment, 2),
            "weight": weights["news_sentiment"],
            "raw": features.get("news_sentiment_rolling_30d"),
        },
        "macro_adjustment": {
            "score": round(macro_adjustment, 2),
            "weight": weights["macro_adjustment"],
            "raw": features.get("macro_context"),
        },
    }
    return round(final_score, 2), contributing_factors


def build_evidence_sentences(contributing_factors: dict[str, Any]) -> list[str]:
    """팩터별 근거 문장 조립 (Phase 4)."""
    raise NotImplementedError("Phase 4")


def compute_snapshot_and_cache(stock_code: str) -> dict[str, Any]:
    """미등록 기업 대상: 전 파이프라인 1회 실행 + Redis 캐싱 (Phase 4).

    반환에는 반드시 기준 시각(as_of)과 만료 시각을 포함한다.
    """
    raise NotImplementedError("Phase 4")
