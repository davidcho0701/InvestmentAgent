"""Redis(Upstash) 캐시. API 캐싱 + 롤링 감성 점수 + 스냅샷 캐시에 공용으로 쓴다."""
from __future__ import annotations

import json
from typing import Any

import redis

from .config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL 이 설정되지 않았습니다 (.env 확인)")
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


# --- 키 네임스페이스 (전 모듈에서 이 함수들만 사용할 것) ---

def snapshot_key(stock_code: str) -> str:
    return f"snapshot:{stock_code}"


def news_rolling_key(corp_code: str) -> str:
    return f"news_sentiment_rolling_30d:{corp_code}"


def api_cache_key(source: str, ident: str) -> str:
    return f"apicache:{source}:{ident}"


# --- JSON 헬퍼 ---

def get_json(key: str) -> Any | None:
    raw = get_client().get(key)
    return json.loads(raw) if raw else None


def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    payload = json.dumps(value, ensure_ascii=False, default=str)
    get_client().set(key, payload, ex=ttl_seconds)


def ping() -> bool:
    try:
        return bool(get_client().ping())
    except Exception:
        return False
