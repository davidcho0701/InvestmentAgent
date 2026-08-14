"""차트 데이터 + 패턴 해설 (Phase 5).

제약: 해설은 어떤 경우에도 매수/매도 권유를 포함하지 않는다. 중립 어미 + "신호 아님" 문구 필수.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket

router = APIRouter(prefix="/api/chart", tags=["chart"])

DISCLAIMER = "본 해설은 차트 형태에 대한 설명이며, 매매 신호가 아닙니다."


@router.get("/{stock_code}")
def get_chart(stock_code: str, user_id: str = Query(...), interval: str = "1m") -> dict:
    """관심종목이면 실시간 캔들, 아니면 과거 OHLCV 기반 정적 캔들 + 해설."""
    raise HTTPException(status_code=501, detail="Phase 5 에서 구현")


@router.websocket("/ws/{stock_code}")
async def chart_ws(websocket: WebSocket, stock_code: str) -> None:
    """관심종목 등록 기업에 한해 실시간 캔들 push."""
    await websocket.accept()
    await websocket.close(code=1011, reason="Phase 5 에서 구현")
