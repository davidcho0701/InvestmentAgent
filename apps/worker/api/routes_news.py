"""LLM 이 생성한 고영향 뉴스 근거 조회 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..core import db, get_logger
from ..pipeline import entity_resolution, news_sentiment

log = get_logger(__name__)

router = APIRouter(prefix="/api/news-evidence", tags=["news"])


@router.post("/{stock_code}/refresh")
def refresh_news_evidence(stock_code: str) -> dict:
    corp_code, company = _resolve_company(stock_code)
    try:
        result = news_sentiment.process_news_batch(corp_code)
    except Exception as exc:
        log.exception("LLM 뉴스 근거 갱신 실패", stock_code=stock_code, corp_code=corp_code)
        raise HTTPException(status_code=502, detail="뉴스 근거 갱신에 실패했습니다.") from exc

    return {
        "stock_code": company["stock_code"] if company else stock_code,
        "corp_name": company["corp_name"] if company else None,
        "result": result,
    }


@router.get("/{stock_code}")
def list_news_evidence(
    stock_code: str,
    limit: int = Query(5, ge=1, le=20, description="조회할 최근 LLM 뉴스 근거 수"),
) -> dict:
    corp_code, company = _resolve_company(stock_code)
    rows = db.fetch_all(
        """
        SELECT title, url, published_at, sentiment_score, topic_tag
        FROM fact_news_sentiment
        WHERE corp_code = :corp_code
          AND sentiment_source = 'llm'
          AND NULLIF(BTRIM(topic_tag), '') IS NOT NULL
        ORDER BY published_at DESC NULLS LAST, id DESC
        LIMIT :limit
        """,
        {"corp_code": corp_code, "limit": limit},
    )

    return {
        "stock_code": company["stock_code"] if company else stock_code,
        "corp_name": company["corp_name"] if company else None,
        "items": [_row_to_item(row) for row in rows],
    }


def _resolve_company(stock_code: str) -> tuple[str, dict | None]:
    corp_code = entity_resolution.resolve_by_name(stock_code)
    if not corp_code:
        raise HTTPException(status_code=404, detail="등록되지 않은 종목입니다.")

    company = db.fetch_one(
        "SELECT stock_code, corp_name FROM dim_company WHERE corp_code = :corp_code",
        {"corp_code": corp_code},
    )
    return corp_code, company


def _row_to_item(row: dict) -> dict:
    return {
        "title": row["title"],
        "url": row["url"],
        "published_at": row["published_at"].isoformat() if row["published_at"] else None,
        "sentiment_score": row["sentiment_score"],
        "evidence": row["topic_tag"],
    }
