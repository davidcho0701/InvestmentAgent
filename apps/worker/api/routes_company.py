"""기업 검색 — CompanySelector(공용 컴포넌트)용 (§9)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..pipeline import entity_resolution

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("/search")
def search_companies(q: str = Query(..., min_length=1), limit: int = 10) -> list[dict]:
    return entity_resolution.search_companies(q, limit=limit)
