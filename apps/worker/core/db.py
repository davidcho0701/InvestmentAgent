"""PostgreSQL(Supabase) 연결. SQLAlchemy Core 기반 — ORM 모델은 두지 않고 SQL 을 직접 쓴다."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from .config import settings

_engine: Engine | None = None


def _coerce(value: Any) -> Any:
    """NUMERIC 컬럼이 psycopg3 에서 Decimal 로 오는데, 그대로 두면 json.dumps 나 다른
    모듈의 float 산술(예: macro_adjustment 의 계수 곱셈)에서 예기치 않게 터진다.
    DB 조회 경계에서 한 번에 float 로 통일해 상위 코드가 Decimal 을 신경 쓰지 않게 한다.
    """
    return float(value) if isinstance(value, Decimal) else value


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL 이 설정되지 않았습니다 (.env 확인)")
        url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        # Supabase 의 커넥션 풀러(Supavisor transaction 모드)는 세션 간 서버사이드
        # prepared statement 를 공유하지 않아, psycopg3 의 기본 statement 캐싱을 켜두면
        # "prepared statement ... already exists" 에러가 난다. prepare_threshold=None 으로
        # 서버사이드 prepare 자체를 꺼서 풀러와 호환되게 한다.
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"prepare_threshold": None},
        )
    return _engine


@contextmanager
def get_connection() -> Iterator[Connection]:
    with get_engine().begin() as conn:
        yield conn


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [{k: _coerce(v) for k, v in r.items()} for r in rows]


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
