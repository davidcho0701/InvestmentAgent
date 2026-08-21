"""관심종목 CRUD (Phase 6). MAX_WATCHLIST_SLOTS 초과 시 명확한 에러, 임의 대체 금지."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core import db, get_logger, settings

log = get_logger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# 담당 B 의 WebSocket 구독 시작/해제 로직이 여기 등록된다
# (§9 Day 0 합의: on_watchlist_add(stock_code) 콜백). B 쪽 모듈에서 import 시점에
# register_on_add / register_on_remove 를 호출해 연결한다.
_on_add_hooks: list[Callable[[str], None]] = []
_on_remove_hooks: list[Callable[[str], None]] = []


def register_on_add(hook: Callable[[str], None]) -> None:
    _on_add_hooks.append(hook)


def register_on_remove(hook: Callable[[str], None]) -> None:
    _on_remove_hooks.append(hook)


def _notify(hooks: list[Callable[[str], None]], stock_code: str, event: str) -> None:
    for hook in hooks:
        try:
            hook(stock_code)
        except Exception:
            log.exception("watchlist 훅 실패", stock_code=stock_code, event=event, hook=hook)


class WatchlistItem(BaseModel):
    corp_code: str
    stock_code: str | None = None
    corp_name: str | None = None
    registered_at: str | None = None


class WatchlistCreate(BaseModel):
    corp_code: str


@router.get("")
def list_watchlist(user_id: str = Query(...)) -> list[WatchlistItem]:
    rows = db.fetch_all(
        """
        SELECT w.corp_code, c.stock_code, c.corp_name, w.registered_at
        FROM user_watchlist w
        JOIN dim_company c ON c.corp_code = w.corp_code
        WHERE w.user_id = :user_id
        ORDER BY w.registered_at
        """,
        {"user_id": user_id},
    )
    return [
        WatchlistItem(
            corp_code=r["corp_code"],
            stock_code=r["stock_code"],
            corp_name=r["corp_name"],
            registered_at=r["registered_at"].isoformat() if r["registered_at"] else None,
        )
        for r in rows
    ]


@router.post("", status_code=201)
def add_watchlist(payload: WatchlistCreate, user_id: str = Query(...)) -> WatchlistItem:
    """슬롯 초과 시 409 + 명확한 메시지. 기존 슬롯을 임의로 대체하지 않는다."""
    company = db.fetch_one(
        "SELECT stock_code, corp_name FROM dim_company WHERE corp_code = :corp_code",
        {"corp_code": payload.corp_code},
    )
    if not company:
        raise HTTPException(status_code=404, detail="존재하지 않는 기업입니다.")

    existing = db.fetch_one(
        "SELECT 1 FROM user_watchlist WHERE user_id = :user_id AND corp_code = :corp_code",
        {"user_id": user_id, "corp_code": payload.corp_code},
    )
    if existing:
        raise HTTPException(status_code=409, detail="이미 관심종목에 등록되어 있어요.")

    count_row = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM user_watchlist WHERE user_id = :user_id", {"user_id": user_id}
    )
    if count_row and count_row["cnt"] >= settings.max_watchlist_slots:
        raise HTTPException(
            status_code=409,
            detail=f"관심종목은 최대 {settings.max_watchlist_slots}개까지 등록할 수 있어요.",
        )

    db.execute(
        "INSERT INTO user_watchlist (user_id, corp_code) VALUES (:user_id, :corp_code)",
        {"user_id": user_id, "corp_code": payload.corp_code},
    )
    if company["stock_code"]:
        _notify(_on_add_hooks, company["stock_code"], "add")

    return WatchlistItem(
        corp_code=payload.corp_code,
        stock_code=company["stock_code"],
        corp_name=company["corp_name"],
    )


@router.delete("/{corp_code}", status_code=204, response_model=None)
def remove_watchlist(corp_code: str, user_id: str = Query(...)) -> None:
    """해제 시 폴링/WS 구독만 해제하고 기존 수집 데이터는 삭제하지 않는다."""
    company = db.fetch_one(
        "SELECT stock_code FROM dim_company WHERE corp_code = :corp_code", {"corp_code": corp_code}
    )
    deleted = db.execute(
        "DELETE FROM user_watchlist WHERE user_id = :user_id AND corp_code = :corp_code",
        {"user_id": user_id, "corp_code": corp_code},
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="관심종목에 등록되어 있지 않아요.")
    if company and company["stock_code"]:
        _notify(_on_remove_hooks, company["stock_code"], "remove")
