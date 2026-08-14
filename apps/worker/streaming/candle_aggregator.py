"""체결 틱 -> OHLCV 캔들 집계 (Phase 5)."""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)

SUPPORTED_INTERVALS = {"1m": 60, "5m": 300, "15m": 900}


def bucket_ts(ts_epoch: int, interval: str = "1m") -> int:
    """체결 시각을 캔들 구간 시작 epoch 로 내림."""
    size = SUPPORTED_INTERVALS[interval]
    return ts_epoch - (ts_epoch % size)


class CandleAggregator:
    """종목별 진행 중 캔들을 메모리에 들고, 구간이 닫히면 DB 적재 + push."""

    def __init__(self, interval: str = "1m") -> None:
        self.interval = interval
        self._open: dict[str, dict[str, Any]] = {}

    def on_tick(self, stock_code: str, price: float, volume: int, ts_epoch: int) -> dict | None:
        """틱 반영. 캔들이 마감되면 마감된 캔들 dict 를 반환, 아니면 None."""
        raise NotImplementedError("Phase 5")

    def flush(self) -> list[dict[str, Any]]:
        """장 마감/종료 시 진행 중 캔들 전부 반환."""
        raise NotImplementedError("Phase 5")
