"""final_score 계산 (§3.2.6). 가중치/정규화 파라미터는 config.yaml 에서 읽는다.

주의: 애널리스트 컨센서스는 final_score 에 절대 섞지 않는다 (§7).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core import cache, db, get_logger, settings
from ..core.config import get_scoring_config

log = get_logger(__name__)


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
    sentences: list[str] = []

    fh = contributing_factors.get("financial_health", {})
    if fh.get("raw") is not None:
        sentences.append(f"재무 건전성 섹터 내 백분위 {round(fh['raw'])}점")
        if fh.get("accrual_penalty", 0) > 0:
            sentences.append(
                f"발생액 비율이 높아 재무 건전성 점수에서 {fh['accrual_penalty']}점 감점"
            )
    else:
        sentences.append("재무 건전성 데이터 없음")

    fg = contributing_factors.get("financial_growth", {})
    if fg.get("raw") is not None:
        direction = "성장" if fg["raw"] >= 0 else "역성장"
        sentences.append(f"전년 대비 매출 {direction} {abs(round(fg['raw'], 1))}%")
    else:
        sentences.append("성장성 데이터 없음")

    ns = contributing_factors.get("news_sentiment", {})
    if ns.get("raw") is not None:
        tone = "긍정 우세" if ns["raw"] > 0.15 else "부정 우세" if ns["raw"] < -0.15 else "중립"
        sentences.append(f"최근 30일 뉴스 감성 {tone}")
    else:
        sentences.append("최근 뉴스 데이터 없음")

    ma = contributing_factors.get("macro_adjustment", {})
    if ma.get("raw") is not None:
        direction = "우호적" if ma["raw"] > 0.1 else "부담 요인" if ma["raw"] < -0.1 else "중립적"
        sentences.append(f"현재 거시환경은 이 업종에 {direction}")
    else:
        sentences.append("거시 조정 데이터 없음")

    return sentences


# 재무건전성 합성 백분위에 사용할 지표 — True 인 항목은 값이 낮을수록 좋으므로 반전한다.
_HEALTH_PERCENTILE_FIELDS: dict[str, bool] = {
    "operating_margin_percentile": False,
    "roe_percentile": False,
    "roa_percentile": False,
    "current_ratio_percentile": False,
    "debt_ratio_percentile": True,
}


def assemble_features(corp_code: str) -> dict[str, Any]:
    """최신 재무/뉴스/거시 데이터를 모아 calculate_final_score() 입력 dict 로 조립한다.

    결측치는 임의 보간하지 않고 None 으로 남겨 normalize_to_score() 가 중립(50점) 처리하게 한다.
    """
    from . import macro_adjustment

    report_row = db.fetch_one(
        "SELECT MAX(report_date) AS d FROM fact_financial_statement WHERE corp_code = :corp_code",
        {"corp_code": corp_code},
    )
    report_date = report_row["d"].isoformat() if report_row and report_row["d"] else None

    financial_rows: dict[str, Any] = {}
    if report_date:
        rows = db.fetch_all(
            """
            SELECT account_id, account_value, sector_percentile_rank, accrual_ratio
            FROM fact_financial_statement
            WHERE corp_code = :corp_code AND report_date = :report_date
            """,
            {"corp_code": corp_code, "report_date": report_date},
        )
        financial_rows = {r["account_id"]: r for r in rows}

    health_values = []
    for field, invert in _HEALTH_PERCENTILE_FIELDS.items():
        metric = field[: -len("_percentile")]
        row = financial_rows.get(metric)
        if row and row.get("sector_percentile_rank") is not None:
            v = row["sector_percentile_rank"]
            health_values.append(100 - v if invert else v)
    sector_percentile_rank = sum(health_values) / len(health_values) if health_values else None

    accrual_ratio = next(
        (r["accrual_ratio"] for r in financial_rows.values() if r.get("accrual_ratio") is not None),
        None,
    )
    yoy_row = financial_rows.get("revenue_yoy")
    yoy_growth = yoy_row["account_value"] if yoy_row else None

    news_cached = cache.get_json(cache.news_rolling_key(corp_code))
    news_sentiment_rolling_30d = news_cached["score"] if news_cached else None

    sector_row = db.fetch_one(
        "SELECT sector FROM dim_company WHERE corp_code = :corp_code", {"corp_code": corp_code}
    )
    macro_context = None
    if sector_row and sector_row.get("sector"):
        macro_context = macro_adjustment.compute_macro_adjustment(sector_row["sector"])

    return {
        "sector_percentile_rank": sector_percentile_rank,
        "accrual_ratio": accrual_ratio,
        "yoy_growth": yoy_growth,
        "news_sentiment_rolling_30d": news_sentiment_rolling_30d,
        "macro_context": macro_context,
        "report_date": report_date,
    }


def rescore_live(corp_code: str, trigger_type: str = "batch") -> dict[str, Any]:
    """관심종목(라이브) 재계산 -> mart_investment_score 저장.

    trigger_type: 'batch'(정기배치) | 'event'(고영향 뉴스 등 즉시 트리거).
    """
    features = assemble_features(corp_code)
    final_score, contributing_factors = calculate_final_score(features)
    label = recommendation_label(final_score)
    now = datetime.now(UTC)

    db.execute(
        """
        INSERT INTO mart_investment_score
            (corp_code, score_date, final_score, contributing_factors,
             recommendation_label, trigger_type)
        VALUES
            (:corp_code, :score_date, :final_score, CAST(:contributing_factors AS jsonb),
             :recommendation_label, :trigger_type)
        """,
        {
            "corp_code": corp_code,
            "score_date": now,
            "final_score": final_score,
            "contributing_factors": json.dumps(contributing_factors, ensure_ascii=False),
            "recommendation_label": label,
            "trigger_type": trigger_type,
        },
    )
    log.info(
        "라이브 스코어 재계산",
        corp_code=corp_code,
        final_score=final_score,
        trigger_type=trigger_type,
    )
    return {
        "final_score": final_score,
        "contributing_factors": contributing_factors,
        "recommendation_label": label,
        "as_of": now.isoformat(),
    }


def compute_snapshot_and_cache(stock_code: str) -> dict[str, Any]:
    """미등록 기업 대상: 전 파이프라인 1회 실행 + Redis 캐싱 (Phase 4).

    반환에는 반드시 기준 시각(as_of)과 만료 시각을 포함한다.
    """
    from . import entity_resolution

    cached = cache.get_json(cache.snapshot_key(stock_code))
    if cached:
        return cached

    corp_code = entity_resolution.resolve_by_name(stock_code)
    if not corp_code:
        raise ValueError(f"등록되지 않은 종목코드/기업명: {stock_code}")

    features = assemble_features(corp_code)
    final_score, contributing_factors = calculate_final_score(features)
    evidence = build_evidence_sentences(contributing_factors)

    now = datetime.now(UTC)
    ttl = settings.snapshot_cache_ttl_seconds
    expires_at = now + timedelta(seconds=ttl)

    response = {
        "final_score": final_score,
        "mode": "snapshot",
        "as_of": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "contributing_factors": contributing_factors,
        "evidence": evidence,
        "recommendation_label": recommendation_label(final_score),
    }

    db.execute(
        """
        INSERT INTO fact_snapshot_score
            (corp_code, requested_at, final_score, contributing_factors, expires_at)
        VALUES
            (:corp_code, :requested_at, :final_score,
             CAST(:contributing_factors AS jsonb), :expires_at)
        ON CONFLICT (corp_code) DO UPDATE
        SET requested_at = EXCLUDED.requested_at,
            final_score = EXCLUDED.final_score,
            contributing_factors = EXCLUDED.contributing_factors,
            expires_at = EXCLUDED.expires_at
        """,
        {
            "corp_code": corp_code,
            "requested_at": now,
            "final_score": final_score,
            "contributing_factors": json.dumps(contributing_factors, ensure_ascii=False),
            "expires_at": expires_at,
        },
    )
    cache.set_json(cache.snapshot_key(stock_code), response, ttl_seconds=ttl)
    return response
