from datetime import date

from apps.worker.pipeline.financial_normalize import (
    calc_accrual_ratio,
    calc_dio,
    calc_dso,
    calc_roe,
    calc_yoy_growth,
    infer_report_params,
    latest_available_report_date,
    normalize_statement,
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


def test_normalize_statement_maps_known_accounts():
    raw = [
        {"account_id": "ifrs-full_Assets", "thstrm_amount": "1,234,567"},
        {"account_id": "ifrs-full_Revenue", "thstrm_amount": "500000"},
        {"account_id": "unknown_account", "thstrm_amount": "999"},
        {"account_id": "ifrs-full_Equity", "thstrm_amount": ""},
    ]
    result = normalize_statement(raw)
    assert result == {"total_assets": 1234567.0, "revenue": 500000.0}


def test_normalize_statement_handles_negative_and_bad_values():
    raw = [
        {"account_id": "ifrs-full_ProfitLoss", "thstrm_amount": "-12,345"},
        {"account_id": "dart_OperatingIncomeLoss", "thstrm_amount": "not-a-number"},
    ]
    result = normalize_statement(raw)
    assert result == {"net_income": -12345.0}


def test_infer_report_params_quarter_end():
    assert infer_report_params("2025-06-30") == ("2025", "11012")
    assert infer_report_params("2025-12-31") == ("2025", "11011")


def test_infer_report_params_non_quarter_end_defaults_to_annual():
    assert infer_report_params("2025-07-15") == ("2025", "11011")


def test_latest_available_report_date_picks_most_recent_filed_quarter():
    # 2026-08-21 기준: Q2(06-30, lag45)는 52일 지나 공시됐고, Q3(09-30)는 아직 미도래
    assert latest_available_report_date(date(2026, 8, 21)) == "2026-06-30"


def test_latest_available_report_date_skips_unfiled_annual_report():
    # 2026-02-01 기준: 2025-12-31 사업보고서는 32일밖에 안 지나 lag(90일) 미충족 -> 직전 분기가 최신
    assert latest_available_report_date(date(2026, 2, 1)) == "2025-09-30"
