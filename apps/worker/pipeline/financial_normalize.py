"""재무 정규화 및 파생지표 계산 (§3.2.2).

순수 계산 함수는 여기서 완결되어 있고, DART 원문 매핑/DB 적재는 Phase 1 에서 채운다.
분모가 0/None 인 경우는 예외 대신 None 을 반환해 상위에서 결측으로 다루게 한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ..core import db, get_logger

log = get_logger(__name__)

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

# DART 표준계정 account_id -> 내부 표준 필드명 매핑. 실제 재무제표 응답을 보며 확장한다.
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


# DART fnlttSinglAcntAll 은 BS/IS(또는 CIS)/CF 외에 자본변동표(SCE)도 같이 내려주는데,
# SCE 는 자본금/이익잉여금/비지배지분 등 구성요소별 행이 'ifrs-full_Equity' 같은
# account_id 를 반복 재사용한다(각 열의 소계). 그대로 두면 재무상태표의 진짜 값을
# 엉뚱한 SCE 구성요소 값으로 덮어써버리므로 정규화 대상에서 제외한다.
_EXCLUDED_SJ_DIV = {"SCE"}


def normalize_statement(raw_accounts: list[dict[str, Any]]) -> dict[str, float]:
    """DART fnlttSinglAcntAll 응답 목록을 내부 표준 필드 dict 로 축약한다."""
    result: dict[str, float] = {}
    for row in raw_accounts:
        if row.get("sj_div") in _EXCLUDED_SJ_DIV:
            continue
        field = ACCOUNT_MAP.get(row.get("account_id"))
        if not field:
            continue
        raw_value = row.get("thstrm_amount")
        if raw_value in (None, ""):
            continue
        try:
            result[field] = float(str(raw_value).replace(",", ""))
        except ValueError:
            log.warning(
                "재무 계정값 파싱 실패", account_id=row.get("account_id"), raw_value=raw_value
            )
    return result


# reprt_code: 11013(1분기) 11012(반기) 11014(3분기) 11011(사업보고서)
# lag_days: DART 법정 제출기한(분기 45일 / 사업보고서 90일) 경과 후에야 공시가 안정적으로 존재한다.
_QUARTER_ENDS: list[tuple[int, int, str, int]] = [
    (3, 31, "11013", 45),
    (6, 30, "11012", 45),
    (9, 30, "11014", 45),
    (12, 31, "11011", 90),
]


def infer_report_params(report_date: str) -> tuple[str, str]:
    """'YYYY-MM-DD' 결산기준일 -> (bsns_year, reprt_code). 분기말이 아니면 사업보고서로 취급한다."""
    year_str, month_str, day_str = report_date.split("-")
    month, day = int(month_str), int(day_str)
    for m, d, reprt_code, _ in _QUARTER_ENDS:
        if (m, d) == (month, day):
            return year_str, reprt_code
    return year_str, "11011"


def latest_available_report_date(today: date | None = None) -> str:
    """오늘 기준 DART 제출기한을 감안했을 때 이미 공시되었을 가장 최근 결산기준일."""
    today = today or date.today()
    candidates = [
        period_end
        for year in (today.year, today.year - 1)
        for month, day, _, lag in _QUARTER_ENDS
        if (period_end := date(year, month, day)) <= today
        and (today - period_end).days >= lag
    ]
    if not candidates:
        return date(today.year - 1, 12, 31).isoformat()
    return max(candidates).isoformat()


def _fetch_period(corp_code: str, bsns_year: str, reprt_code: str, fs_div: str) -> dict[str, float]:
    from ..ingestion import dart_client

    raw = dart_client.fetch_financial_statement(corp_code, bsns_year, reprt_code, fs_div)
    return normalize_statement(raw) if raw else {}


_PERCENTILE_METRICS = ("operating_margin", "roe", "roa", "debt_ratio", "current_ratio")


def _sector_percentile_ranks(
    corp_code: str, report_date: str, features: dict[str, Any]
) -> dict[str, float | None]:
    row = db.fetch_one(
        "SELECT sector FROM dim_company WHERE corp_code = :corp_code", {"corp_code": corp_code}
    )
    sector = row["sector"] if row else None
    if not sector:
        return {f"{metric}_percentile": None for metric in _PERCENTILE_METRICS}

    ranks: dict[str, float | None] = {}
    for metric in _PERCENTILE_METRICS:
        peers = db.fetch_all(
            """
            SELECT ffs.account_value
            FROM fact_financial_statement ffs
            JOIN dim_company c ON c.corp_code = ffs.corp_code
            WHERE c.sector = :sector
              AND ffs.account_id = :metric
              AND ffs.report_date = :report_date
              AND ffs.corp_code <> :corp_code
              AND ffs.account_value IS NOT NULL
            """,
            {
                "sector": sector,
                "metric": metric,
                "report_date": report_date,
                "corp_code": corp_code,
            },
        )
        peer_values = [p["account_value"] for p in peers]
        ranks[f"{metric}_percentile"] = percentile_rank(features.get(metric), peer_values)
    return ranks


def build_financial_features(corp_code: str, report_date: str) -> dict[str, Any]:
    """정규화 -> 파생지표 -> 섹터 백분위까지 계산한 피처 dict 를 반환한다.

    재무제표가 아직 공시되지 않은 경우(§8-4 결측치 원칙) 빈 dict 를 반환한다 — 임의 보간하지 않는다.
    """
    from ..ingestion import dart_client

    bsns_year, reprt_code = infer_report_params(report_date)

    raw_accounts = dart_client.fetch_financial_statement(corp_code, bsns_year, reprt_code, "CFS")
    fs_div_used = "CFS"
    if not raw_accounts:
        raw_accounts = dart_client.fetch_financial_statement(
            corp_code, bsns_year, reprt_code, "OFS"
        )
        fs_div_used = "OFS"
    if not raw_accounts:
        log.info("재무제표 없음 — 결측 처리", corp_code=corp_code, report_date=report_date)
        return {}

    current = normalize_statement(raw_accounts)
    prev_year = str(int(bsns_year) - 1)
    previous = _fetch_period(corp_code, prev_year, reprt_code, fs_div_used)

    features: dict[str, Any] = dict(current)
    features["fs_div"] = fs_div_used
    features["source_rcp_no"] = raw_accounts[0].get("rcept_no")

    features["operating_margin"] = calc_operating_margin(
        current.get("operating_income"), current.get("revenue")
    )
    features["roe"] = calc_roe(current.get("net_income"), current.get("total_equity"))
    features["roa"] = calc_roa(current.get("net_income"), current.get("total_assets"))
    features["debt_ratio"] = calc_debt_ratio(
        current.get("total_liabilities"), current.get("total_equity")
    )
    features["current_ratio"] = calc_current_ratio(
        current.get("current_assets"), current.get("current_liabilities")
    )
    features["accrual_ratio"] = calc_accrual_ratio(
        current.get("net_income"), current.get("operating_cashflow"), current.get("total_assets")
    )
    features["dso"] = calc_dso(current.get("receivables"), current.get("revenue"))
    features["dio"] = calc_dio(current.get("inventory"), current.get("cogs"))
    features["revenue_yoy"] = (
        calc_yoy_growth(current.get("revenue"), previous.get("revenue")) if previous else None
    )
    features["net_income_yoy"] = (
        calc_yoy_growth(current.get("net_income"), previous.get("net_income")) if previous else None
    )

    features.update(_sector_percentile_ranks(corp_code, report_date, features))
    return features


# fact_financial_statement 는 (corp_code, report_date, account_id) 단위 롱포맷 —
# 계정 원본값과 파생비율을 같은 테이블에 "가짜 account_id"(예: 'roe')로 함께 저장한다.
_NON_ACCOUNT_KEYS = {"fs_div", "source_rcp_no", "accrual_ratio", "dso", "dio"}


def save_financial_statement(corp_code: str, report_date: str, features: dict[str, Any]) -> int:
    """build_financial_features() 결과를 fact_financial_statement 에 upsert 한다."""
    if not features:
        return 0

    accrual_ratio = features.get("accrual_ratio")
    dso = features.get("dso")
    dio = features.get("dio")
    source_rcp_no = features.get("source_rcp_no")
    percentile_by_metric = {
        key[: -len("_percentile")]: value
        for key, value in features.items()
        if key.endswith("_percentile")
    }
    skip_keys = _NON_ACCOUNT_KEYS | set(percentile_by_metric) | {
        f"{m}_percentile" for m in percentile_by_metric
    }

    rows = [
        {
            "corp_code": corp_code,
            "report_date": report_date,
            "account_id": account_id,
            "account_value": value,
            "sector_percentile_rank": percentile_by_metric.get(account_id),
            "accrual_ratio": accrual_ratio,
            "dso": dso,
            "dio": dio,
            "source_rcp_no": source_rcp_no,
        }
        for account_id, value in features.items()
        if account_id not in skip_keys and value is not None
    ]
    if not rows:
        return 0

    db.execute(
        """
        INSERT INTO fact_financial_statement
            (corp_code, report_date, account_id, account_value, sector_percentile_rank,
             accrual_ratio, dso, dio, source_rcp_no)
        VALUES
            (:corp_code, :report_date, :account_id, :account_value, :sector_percentile_rank,
             :accrual_ratio, :dso, :dio, :source_rcp_no)
        ON CONFLICT (corp_code, report_date, account_id) DO UPDATE
        SET account_value = EXCLUDED.account_value,
            sector_percentile_rank = EXCLUDED.sector_percentile_rank,
            accrual_ratio = EXCLUDED.accrual_ratio,
            dso = EXCLUDED.dso,
            dio = EXCLUDED.dio,
            source_rcp_no = EXCLUDED.source_rcp_no
        """,
        rows,
    )
    return len(rows)
