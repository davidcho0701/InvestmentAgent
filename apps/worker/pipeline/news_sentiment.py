"""뉴스 감성분석 (§3.2.3, Phase 2).

로컬 CPU 추론(KR-FinBERT)이 기본. 고영향 기사에 한해서만 LLM 으로 근거 문장을 생성한다.
모델은 서버 기동 시 1회만 로드한다.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from ..core import cache, db, get_logger, settings

log = get_logger(__name__)

MODEL_NAME = "snunlp/KR-FinBert-SC"

_pipeline = None

_LABEL_SIGN = {"positive": 1, "negative": -1, "neutral": 0}

_LLM_API_URL = "https://api.anthropic.com/v1/messages"
_LLM_API_VERSION = "2023-06-01"


def get_sentiment_pipeline():
    """transformers pipeline 지연 로딩 (프로세스당 1회)."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline as hf_pipeline

        log.info("감성분석 모델 로딩", model=MODEL_NAME)
        _pipeline = hf_pipeline("sentiment-analysis", model=MODEL_NAME, device=-1)
    return _pipeline


def analyze_sentiment(text: str) -> float:
    """-1(부정) ~ +1(긍정) 연속값으로 변환."""
    if not text:
        return 0.0
    result = get_sentiment_pipeline()(text[:512])[0]
    sign = _LABEL_SIGN.get(str(result.get("label", "")).lower(), 0)
    return sign * float(result.get("score", 0.0))


def is_high_impact(sentiment_score: float) -> bool:
    """config.yaml news.high_impact_threshold 기준 고영향 판정."""
    from ..core.config import get_scoring_config

    threshold = get_scoring_config()["news"]["high_impact_threshold"]
    return abs(sentiment_score) > threshold


def generate_evidence_with_llm(title: str, body: str) -> str:
    """고영향 기사에 한해 LLM 으로 근거 문장 1~2줄 생성. 호출 최소화."""
    if not settings.llm_api_key:
        log.warning("LLM_API_KEY 미설정 — 근거 문장 생성 스킵")
        return ""

    prompt = (
        "다음은 상장기업 관련 고영향 뉴스입니다. 투자자가 참고할 수 있도록 "
        "이 뉴스가 왜 중요한지 한국어 1~2문장으로 중립적으로 요약하세요. "
        "매수/매도 권유 표현은 쓰지 마세요.\n\n"
        f"제목: {title}\n본문: {body[:1500]}"
    )
    headers = {
        "x-api-key": settings.llm_api_key,
        "anthropic-version": _LLM_API_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(_LLM_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        log.exception("LLM 근거 문장 생성 실패", title=title)
        return ""

    parts = data.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def update_rolling_sentiment(corp_code: str) -> float:
    """최근 30일 기사에 시간가중 반감기를 적용한 롤링 점수 계산 + Redis 갱신."""
    from ..core.config import get_scoring_config

    cfg = get_scoring_config()["news"]
    window_days = cfg["rolling_window_days"]
    half_life = cfg["time_decay_half_life_days"]

    rows = db.fetch_all(
        """
        SELECT sentiment_score, published_at
        FROM fact_news_sentiment
        WHERE corp_code = :corp_code
          AND published_at >= now() - (:window_days || ' days')::interval
          AND sentiment_score IS NOT NULL
        """,
        {"corp_code": corp_code, "window_days": window_days},
    )

    score = 0.0
    if rows:
        now = datetime.now(UTC)
        weighted_sum = 0.0
        weight_total = 0.0
        for row in rows:
            age_days = (now - row["published_at"]).total_seconds() / 86400
            weight = 0.5 ** (age_days / half_life)
            weighted_sum += row["sentiment_score"] * weight
            weight_total += weight
        score = weighted_sum / weight_total if weight_total else 0.0

    cache.set_json(
        cache.news_rolling_key(corp_code), {"score": score, "n": len(rows)}, ttl_seconds=3600
    )
    return score


def process_news_batch(corp_code: str) -> dict[str, Any]:
    """검색 -> 중복제거 -> 감성분석 -> 저장 -> 롤링 갱신 까지의 단일 진입점."""
    from ..ingestion import naver_news_client

    company = db.fetch_one(
        "SELECT corp_name FROM dim_company WHERE corp_code = :corp_code", {"corp_code": corp_code}
    )
    if not company:
        log.warning("dim_company 에 없는 corp_code", corp_code=corp_code)
        return {"corp_code": corp_code, "collected": 0, "saved": 0, "high_impact": 0}

    articles = naver_news_client.search_news(company["corp_name"])
    deduped = naver_news_client.dedup_articles(articles)

    saved = 0
    high_impact = 0
    for article in deduped:
        url = article.get("url")
        if not url:
            continue

        body = naver_news_client.fetch_article_body(url)
        text = body or article.get("description") or article.get("title", "")
        sentiment_score = analyze_sentiment(text)

        topic_tag = None
        sentiment_source = "local"
        if body and is_high_impact(sentiment_score):
            high_impact += 1
            evidence = generate_evidence_with_llm(article.get("title", ""), body)
            if evidence:
                topic_tag = evidence
                sentiment_source = "llm"

        db.execute(
            """
            INSERT INTO fact_news_sentiment
                (corp_code, published_at, title, url, sentiment_score,
                 topic_tag, dedup_group_id, sentiment_source)
            VALUES
                (:corp_code, :published_at, :title, :url, :sentiment_score,
                 :topic_tag, :dedup_group_id, :sentiment_source)
            ON CONFLICT (url) DO UPDATE
            SET sentiment_score = EXCLUDED.sentiment_score,
                topic_tag = EXCLUDED.topic_tag,
                sentiment_source = EXCLUDED.sentiment_source
            """,
            {
                "corp_code": corp_code,
                "published_at": article.get("published_at"),
                "title": article.get("title"),
                "url": url,
                "sentiment_score": sentiment_score,
                "topic_tag": topic_tag,
                "dedup_group_id": article.get("dedup_group_id"),
                "sentiment_source": sentiment_source,
            },
        )
        saved += 1

    rolling_score = update_rolling_sentiment(corp_code)
    result = {
        "corp_code": corp_code,
        "collected": len(articles),
        "saved": saved,
        "high_impact": high_impact,
        "rolling_score": rolling_score,
    }

    if high_impact > 0:
        from . import scoring

        try:
            scoring.rescore_live(corp_code, trigger_type="event")
        except Exception:
            log.exception("고영향 뉴스 즉시 재계산 실패", corp_code=corp_code)

    return result
