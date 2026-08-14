"""GET /api/score/{stock_code} — 관심종목 여부에 따라 라이브/스냅샷 자동 분기 (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/score", tags=["score"])


@router.get("/{stock_code}")
def get_score(stock_code: str, user_id: str = Query(..., description="사용자 식별자")) -> dict:
    """관심종목이면 mart_investment_score(라이브), 아니면 스냅샷 캐시/재계산.

    스냅샷 응답에는 반드시 기준 시각(as_of)을 포함해 실시간과 혼동되지 않게 한다.
    """
    raise HTTPException(status_code=501, detail="Phase 4 에서 구현")
