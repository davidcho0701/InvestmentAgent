"""네이버 뉴스 검색 + 본문 크롤링 (Phase 2).

크롤링 전 대상 도메인 robots.txt 를 확인하고, 허용되지 않으면 제목/요약만 사용한다.
"""
from __future__ import annotations

import hashlib
import re
import urllib.robotparser as robotparser
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..core import cache, get_logger, settings

log = get_logger(__name__)

# 네이버 검색 Open API 는 NAVER API HUB(NCP)로 이관되어, 구 developers.naver.com 방식
# (X-Naver-Client-Id/Secret, openapi.naver.com) 이 아니라 NCP API Gateway 인증
# (X-NCP-APIGW-API-KEY-ID/KEY, naverapihub.apigw.ntruss.com) 을 쓴다. 응답 JSON(items 등)은 동일.
SEARCH_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
_USER_AGENT = "InvestScopeBot/0.1 (+https://github.com/; contact: dev@investscope.local)"

# 본문 추출용 CSS 셀렉터 (국내 주요 언론사/포털 공통 패턴 우선순위)
_BODY_SELECTORS = (
    "#dic_area", "#newsct_article", "article", ".article_body", "#articleBodyContents"
)


def _strip_html(text: str) -> str:
    return BeautifulSoup(text or "", "html.parser").get_text()


def _parse_pubdate(pub_date: str | None) -> str | None:
    if not pub_date:
        return None
    try:
        return parsedate_to_datetime(pub_date).isoformat()
    except (TypeError, ValueError):
        return None


def search_news(query: str, display: int = 50, start: int = 1) -> list[dict[str, Any]]:
    """기업명/별칭으로 뉴스 검색. 반환: [{title, url, description, published_at}]."""
    headers = {
        "X-NCP-APIGW-API-KEY-ID": settings.naver_client_id,
        "X-NCP-APIGW-API-KEY": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "start": start, "sort": "date"}
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(SEARCH_URL, headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()

    results = []
    for item in payload.get("items", []):
        results.append(
            {
                "title": _strip_html(item.get("title", "")),
                "url": item.get("originallink") or item.get("link"),
                "description": _strip_html(item.get("description", "")),
                "published_at": _parse_pubdate(item.get("pubDate")),
            }
        )
    return results


def is_crawl_allowed(url: str) -> bool:
    """robots.txt 확인 (결과는 도메인 단위로 캐시)."""
    domain = urlparse(url).netloc
    if not domain:
        return False

    cache_key = cache.api_cache_key("robots", domain)
    cached = cache.get_json(cache_key)
    if cached is not None:
        return bool(cached.get("allowed"))

    allowed = False
    try:
        rp = robotparser.RobotFileParser()
        rp.set_url(f"https://{domain}/robots.txt")
        rp.read()
        allowed = rp.can_fetch("*", url)
    except Exception:
        log.warning("robots.txt 확인 실패 — 크롤링 불허로 처리", domain=domain)
        allowed = False

    cache.set_json(cache_key, {"allowed": allowed}, ttl_seconds=86400)
    return allowed


def fetch_article_body(url: str) -> str | None:
    """BeautifulSoup 본문 추출. 크롤링 불허 시 None."""
    if not is_crawl_allowed(url):
        return None

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
    except httpx.HTTPError:
        log.warning("기사 본문 요청 실패", url=url)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for selector in _BODY_SELECTORS:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(separator=" ", strip=True)
            if text:
                return text

    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
    text = " ".join(t for t in paragraphs if t)
    return text or None


# --- 중복기사 제거 (제목 MinHash) ---

_SHINGLE_SIZE = 3
_NUM_HASHES = 32
_SIMILARITY_THRESHOLD = 0.6


def _shingles(text: str) -> set[str]:
    cleaned = re.sub(r"\s+", "", text or "")
    if len(cleaned) < _SHINGLE_SIZE:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + _SHINGLE_SIZE] for i in range(len(cleaned) - _SHINGLE_SIZE + 1)}


def _minhash_signature(shingles: set[str]) -> tuple[int, ...]:
    if not shingles:
        return tuple([0] * _NUM_HASHES)
    return tuple(
        min(int(hashlib.md5(f"{i}:{s}".encode()).hexdigest(), 16) for s in shingles)
        for i in range(_NUM_HASHES)
    )


def _signature_similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b:
        return 0.0
    return sum(1 for x, y in zip(a, b, strict=False) if x == y) / len(a)


def dedup_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """제목 임베딩 cosine similarity 또는 MinHash 로 중복 기사 그룹핑.

    각 기사에 dedup_group_id 를 부여하고 그룹 대표(최초 기사)만 반환한다.
    """
    signatures = [_minhash_signature(_shingles(a.get("title", ""))) for a in articles]
    group_ids: list[str | None] = [None] * len(articles)
    representatives: list[dict[str, Any]] = []

    for i, article in enumerate(articles):
        if group_ids[i] is not None:
            continue
        group_id = f"grp-{i}"
        group_ids[i] = group_id
        for j in range(i + 1, len(articles)):
            if group_ids[j] is None and _signature_similarity(signatures[i], signatures[j]) >= (
                _SIMILARITY_THRESHOLD
            ):
                group_ids[j] = group_id
        rep = dict(article)
        rep["dedup_group_id"] = group_id
        representatives.append(rep)

    return representatives
