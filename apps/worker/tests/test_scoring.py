from apps.worker.pipeline.scoring import (
    accrual_penalty,
    calculate_final_score,
    normalize_to_score,
    recommendation_label,
)


def test_normalize_clamps():
    assert normalize_to_score(50, 0, 100) == 50.0
    assert normalize_to_score(-999, 0, 100) == 0.0
    assert normalize_to_score(999, 0, 100) == 100.0


def test_normalize_missing_is_neutral():
    assert normalize_to_score(None, 0, 100) == 50.0


def test_accrual_penalty_below_threshold():
    assert accrual_penalty(0.05) == 0.0
    assert accrual_penalty(None) == 0.0


def test_accrual_penalty_scales_and_caps():
    assert accrual_penalty(0.15) == 5.0
    assert accrual_penalty(0.99) == 20.0


def test_final_score_weights_sum_correctly():
    # 모든 팩터가 최고값이면 100 에 수렴
    score, factors = calculate_final_score(
        {
            "sector_percentile_rank": 100,
            "accrual_ratio": 0.0,
            "yoy_growth": 30,
            "news_sentiment_rolling_30d": 1.0,
            "macro_context": 1.0,
        }
    )
    assert score == 100.0
    assert set(factors) == {
        "financial_health",
        "financial_growth",
        "news_sentiment",
        "macro_adjustment",
    }


def test_final_score_all_missing_is_neutral():
    score, _ = calculate_final_score({})
    assert score == 50.0


def test_recommendation_label_bands():
    assert recommendation_label(90) == "긍정적 신호 우세"
    assert recommendation_label(50) == "중립"
    assert recommendation_label(10) == "부정적 신호 우세"
