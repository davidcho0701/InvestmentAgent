"""관심종목 CRUD (Phase 6). MAX_WATCHLIST_SLOTS 초과 시 명확한 에러, 임의 대체 금지."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistItem(BaseModel):
    corp_code: str
    stock_code: str | None = None
    corp_name: str | None = None
    registered_at: str | None = None


class WatchlistCreate(BaseModel):
    corp_code: str


@router.get("")
def list_watchlist(user_id: str = Query(...)) -> list[WatchlistItem]:
    raise HTTPException(status_code=501, detail="Phase 6 에서 구현")


@router.post("", status_code=201)
def add_watchlist(payload: WatchlistCreate, user_id: str = Query(...)) -> WatchlistItem:
    """슬롯 초과 시 409 + 명확한 메시지. 기존 슬롯을 임의로 대체하지 않는다."""
    raise HTTPException(status_code=501, detail="Phase 6 에서 구현")


@router.delete("/{corp_code}", status_code=204)
def remove_watchlist(corp_code: str, user_id: str = Query(...)) -> None:
    """해제 시 폴링/WS 구독만 해제하고 기존 수집 데이터는 삭제하지 않는다."""
    raise HTTPException(status_code=501, detail="Phase 6 에서 구현")
