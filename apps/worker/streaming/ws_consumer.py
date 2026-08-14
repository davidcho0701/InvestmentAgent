"""KIS WebSocket 실시간 체결 소비자 (Phase 5).

관심종목으로 등록된 종목만 구독한다. 등록/해제 시 구독을 동적으로 갱신한다.
"""
from __future__ import annotations

import asyncio

from ..core import get_logger

log = get_logger(__name__)

REAL_WS = "ws://ops.koreainvestment.com:21000"
MOCK_WS = "ws://ops.koreainvestment.com:31000"

TR_ID_TRADE = "H0STCNT0"   # 실시간 체결가
TR_ID_QUOTE = "H0STASP0"   # 실시간 호가


class KisWebSocketConsumer:
    """접속 -> 인증 -> 구독 -> 재연결(지수 백오프) 루프를 담당."""

    def __init__(self) -> None:
        self._subscribed: set[str] = set()

    async def connect(self) -> None:
        raise NotImplementedError("Phase 5")

    async def subscribe(self, stock_code: str) -> None:
        raise NotImplementedError("Phase 5")

    async def unsubscribe(self, stock_code: str) -> None:
        raise NotImplementedError("Phase 5")

    async def run(self) -> None:
        """재연결 백오프를 포함한 메인 루프."""
        raise NotImplementedError("Phase 5")


if __name__ == "__main__":
    asyncio.run(KisWebSocketConsumer().run())
