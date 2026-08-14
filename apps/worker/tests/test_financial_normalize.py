from apps.worker.pipeline.financial_normalize import (
    calc_accrual_ratio,
    calc_dio,
    calc_dso,
    calc_roe,
    calc_yoy_growth,
    percentile_rank,
)


def test_accrual_ratio():
    # 순이익 100, 영업현금흐름 60, 총자산 1000 -> 0.04
    assert calc_accrual_ratio(100, 60, 1000) == 0.04


def test_accrual_ratio_handles_zero_assets():
    assert calc_accrual_ratio(100, 60, 0) is None


def test_dso_dio():
    assert round(calc_dso(100, 365), 2) == 100.0
    assert round(calc_dio(50, 365), 2) == 50.0


def test_roe_percent():
    assert calc_roe(20, 200) == 10.0


def test_yoy_growth_with_negative_base():
    # 전년 -100 -> 올해 -50 은 개선(+50%)
    assert calc_yoy_growth(-50, -100) == 50.0


def test_percentile_rank():
    assert percentile_rank(5, [1, 2, 3, 4, 5]) == 90.0
    assert percentile_rank(None, [1, 2]) is None
    assert percentile_rank(1, []) is None
