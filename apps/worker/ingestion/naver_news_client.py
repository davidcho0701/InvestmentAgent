"""네이버 뉴스 검색 + 본문 크롤링 (Phase 2).

크롤링 전 대상 도메인 robots.txt 를 확인하고, 허용되지 않으면 제목/요약만 사용한다.
"""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)

SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"


def search_news(query: str, display: int = 50, start: int = 1) -> list[dict[str, Any]]:
    """기업명/별칭으로 뉴스 검색. 반환: [{title, url, description, published_at}]."""
    raise NotImplementedError("Phase 2")


def is_crawl_allowed(url: str) -> bool:
    """robots.txt 확인 (결과는 도메인 단위로 캐시)."""
    raise NotImplementedError("Phase 2")


def fetch_article_body(url: str) -> str | None:
    """BeautifulSoup 본문 추출. 크롤링 불허 시 None."""
    raise NotImplementedError("Phase 2")


def dedup_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """제목 임베딩 cosine similarity 또는 MinHash 로 중복 기사 그룹핑.

    각 기사에 dedup_group_id 를 부여하고 그룹 대표만 반환한다.
    """
    raise NotImplementedError("Phase 2")
