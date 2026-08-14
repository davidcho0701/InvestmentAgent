"""재무 정규화 및 파생지표 계산 (§3.2.2).

순수 계산 함수는 여기서 완결되어 있고, DART 원문 매핑/DB 적재는 Phase 1 에서 채운다.
분모가 0/None 인 경우는 예외 대신 None 을 반환해 상위에서 결측으로 다루게 한다.
"""
from __future__ import annotations

from typing import Any

Number = float | int | None


def _safe_div(numerator: Number, denominator: Number) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


# --- §6 핵심 계산 로직 ---

def calc_accrual_ratio(
    net_income: Number, operating_cashflow: Number, total_assets: Number
) -> float | None:
    """발생액 비율. 높을수록 이익의 질이 낮다(현금 뒷받침 없는 회계이익)."""
    if net_income is None or operating_cashflow is None:
        return None
    return _safe_div(float(net_income) - float(operating_cashflow), total_assets)


def calc_dso(receivables: Number, revenue: Number) -> float | None:
    """매출채권회수기간(일)."""
    ratio = _safe_div(receivables, revenue)
    return ratio * 365 if ratio is not None else None


def calc_dio(inventory: Number, cogs: Number) -> float | None:
    """재고자산회전기간(일)."""
    ratio = _safe_div(inventory, cogs)
    return ratio * 365 if ratio is not None else None


# --- 수익성/안정성 지표 ---

def calc_operating_margin(operating_income: Number, revenue: Number) -> float | None:
    ratio = _safe_div(operating_income, revenue)
    return ratio * 100 if ratio is not None else None


def calc_roe(net_income: Number, total_equity: Number) -> float | None:
    ratio = _safe_div(net_income, total_equity)
    return ratio * 100 if ratio is not None else None


def calc_roa(net_income: Number, total_assets: Number) -> float | None:
    ratio = _safe_div(net_income, total_assets)
    return ratio * 100 if ratio is not None else None


def calc_debt_ratio(total_liabilities: Number, total_equity: Number) -> float | None:
    ratio = _safe_div(total_liabilities, total_equity)
    return ratio * 100 if ratio is not None else None


def calc_current_ratio(current_assets: Number, current_liabilities: Number) -> float | None:
    ratio = _safe_div(current_assets, current_liabilities)
    return ratio * 100 if ratio is not None else None


def calc_yoy_growth(current: Number, previous: Number) -> float | None:
    """전년동기 대비 성장률(%). 전년값이 음수면 부호가 뒤집히므로 절댓값으로 나눈다."""
    if current is None or previous in (None, 0):
        return None
    return (float(current) - float(previous)) / abs(float(previous)) * 100


def percentile_rank(value: Number, peer_values: list[float]) -> float | None:
    """섹터 내 백분위(0~100). peer_values 는 결측 제거된 동종업계 값 목록."""
    if value is None or not peer_values:
        return None
    below = sum(1 for v in peer_values if v < value)
    equal = sum(1 for v in peer_values if v == value)
    return (below + 0.5 * equal) / len(peer_values) * 100


# --- Phase 1 에서 구현 ---

# DART 표준계정 account_id -> 내부 표준 필드명 매핑. Phase 1 에서 실제 재무제표 응답을 보며 확장한다.
ACCOUNT_MAP: dict[str, str] = {
    "ifrs-full_Assets": "total_assets",
    "ifrs-full_Liabilities": "total_liabilities",
    "ifrs-full_Equity": "total_equity",
    "ifrs-full_Revenue": "revenue",
    "dart_OperatingIncomeLoss": "operating_income",
    "ifrs-full_ProfitLoss": "net_income",
    "ifrs-full_Inventories": "inventory",
    "ifrs-full_CurrentTradeReceivables": "receivables",
    "ifrs-full_CostOfSales": "cogs",
    "ifrs-full_CurrentAssets": "current_assets",
    "ifrs-full_CurrentLiabilities": "current_liabilities",
    "ifrs-full_CashFlowsFromUsedInOperatingActivities": "operating_cashflow",
}


def normalize_statement(raw_accounts: list[dict[str, Any]]) -> dict[str, float]:
    """DART fnlttSinglAcntAll 응답 목록을 내부 표준 필드 dict 로 축약한다."""
    raise NotImplementedError("Phase 1")


def build_financial_features(corp_code: str, report_date: str) -> dict[str, Any]:
    """정규화 -> 파생지표 -> 섹터 백분위까지 계산한 피처 dict 를 반환한다."""
    raise NotImplementedError("Phase 1")
