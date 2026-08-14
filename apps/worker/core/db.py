"""PostgreSQL(Supabase) 연결. SQLAlchemy Core 기반 — ORM 모델은 두지 않고 SQL 을 직접 쓴다."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from .config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL 이 설정되지 않았습니다 (.env 확인)")
        url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    return _engine


@contextmanager
def get_connection() -> Iterator[Connection]:
    with get_engine().begin() as conn:
        yield conn


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [dict(r) for r in rows]


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: dict[str, Any] | list[dict[str, Any]] | None = None) -> int:
    with get_connection() as conn:
        result = conn.execute(text(sql), params or {})
    return result.rowcount


def ping() -> bool:
    try:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
