"""Aggregate KIS public execution ticks into per-symbol one-minute OHLCV candles."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.worker.ingestion.kis_client import validate_stock_code
from apps.worker.streaming.ws_consumer import DomesticExecutionTick

logger = logging.getLogger(__name__)

KOREA_TIMEZONE = timezone(timedelta(hours=9), name="KST")
CANDLE_INTERVAL = timedelta(minutes=1)
CandleHandler = Callable[["OHLCVCandle"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class OHLCVCandle:
    """One completed or in-progress minute of a domestic stock's executions."""

    stock_code: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    bid_price: Decimal | None
    ask_price: Decimal | None

    def as_dict(self) -> dict[str, str | int | None]:
        """A JSON-safe representation shared by future API and WebSocket routes."""

        return {
            "stock_code": self.stock_code,
            "timestamp": self.timestamp.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "bid_price": str(self.bid_price) if self.bid_price is not None else None,
            "ask_price": str(self.ask_price) if self.ask_price is not None else None,
        }


@dataclass(slots=True)
class _OpenCandle:
    stock_code: str
    bucket_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    bid_price: Decimal | None
    ask_price: Decimal | None
    first_tick_at: datetime
    last_tick_at: datetime
    seen_ticks: set[tuple[object, ...]] = field(default_factory=set)

    @classmethod
    def from_tick(cls, tick: DomesticExecutionTick, tick_at: datetime) -> "_OpenCandle":
        return cls(
            stock_code=tick.stock_code,
            bucket_start=_minute_bucket(tick_at),
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            # KIS H0STCNT0 index 12 is execution volume; index 13 is cumulative
            # daily volume, so only index 12 may be summed for an OHLCV candle.
            volume=tick.execution_volume,
            bid_price=tick.bid_price,
            ask_price=tick.ask_price,
            first_tick_at=tick_at,
            last_tick_at=tick_at,
            seen_ticks={_tick_identity(tick)},
        )

    def add(self, tick: DomesticExecutionTick, tick_at: datetime) -> bool:
        """Merge a new execution, returning false when it is a duplicate."""

        identity = _tick_identity(tick)
        if identity in self.seen_ticks:
            logger.debug("Ignoring duplicate KIS execution: %s", tick.stock_code)
            return False

        self.seen_ticks.add(identity)
        self.high = max(self.high, tick.price)
        self.low = min(self.low, tick.price)
        self.volume += tick.execution_volume

        # An execution can arrive out of order.  Preserve chronological open/close
        # instead of letting arrival order corrupt the candle's defining values.
        if tick_at < self.first_tick_at:
            self.open = tick.price
            self.first_tick_at = tick_at
        if tick_at >= self.last_tick_at:
            self.close = tick.price
            self.bid_price = tick.bid_price
            self.ask_price = tick.ask_price
            self.last_tick_at = tick_at
        return True

    def freeze(self) -> OHLCVCandle:
        return OHLCVCandle(
            stock_code=self.stock_code,
            timestamp=self.bucket_start,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            bid_price=self.bid_price,
            ask_price=self.ask_price,
        )


class CandleAggregator:
    """Maintain isolated open-candle state for many stock codes."""

    def __init__(self, *, on_candle_finalized: CandleHandler | None = None) -> None:
        self._on_candle_finalized = on_candle_finalized
        self._open_candles: dict[str, _OpenCandle] = {}
        self._lock = asyncio.Lock()

    async def ingest(self, tick: DomesticExecutionTick) -> OHLCVCandle | None:
        """Add one execution and finalize its preceding candle after a minute rolls."""

        code = validate_stock_code(tick.stock_code)
        tick_at = execution_datetime(tick)
        finalized: OHLCVCandle | None = None

        async with self._lock:
            current = self._open_candles.get(code)
            if current is None:
                self._open_candles[code] = _OpenCandle.from_tick(tick, tick_at)
                return None

            bucket = _minute_bucket(tick_at)
            if bucket < current.bucket_start:
                logger.warning(
                    "Ignoring late execution from a finalized minute: stock=%s time=%s",
                    code,
                    tick.execution_time,
                )
                return None
            if bucket > current.bucket_start:
                finalized = current.freeze()
                self._open_candles[code] = _OpenCandle.from_tick(tick, tick_at)
            else:
                current.add(tick, tick_at)

        if finalized is not None:
            logger.info(
                "Candle finalized: stock=%s ts=%s o=%s h=%s l=%s c=%s volume=%s",
                finalized.stock_code,
                finalized.timestamp.isoformat(),
                finalized.open,
                finalized.high,
                finalized.low,
                finalized.close,
                finalized.volume,
            )
            await self._notify_finalized(finalized)
        return finalized

    async def current_candle(self, stock_code: str) -> OHLCVCandle | None:
        """Return a snapshot of a symbol's open minute without finalizing it."""

        code = validate_stock_code(stock_code)
        async with self._lock:
            candle = self._open_candles.get(code)
            return candle.freeze() if candle is not None else None

    async def current_candles(self) -> list[OHLCVCandle]:
        """Return independent snapshots of all in-progress candles."""

        async with self._lock:
            return [self._open_candles[code].freeze() for code in sorted(self._open_candles)]

    async def flush(self) -> list[OHLCVCandle]:
        """Finalize all open candles for graceful worker shutdown."""

        async with self._lock:
            finalized = [self._open_candles[code].freeze() for code in sorted(self._open_candles)]
            self._open_candles.clear()
        for candle in finalized:
            logger.info("Candle finalized during shutdown: stock=%s ts=%s", candle.stock_code, candle.timestamp.isoformat())
            await self._notify_finalized(candle)
        return finalized

    async def _notify_finalized(self, candle: OHLCVCandle) -> None:
        if self._on_candle_finalized is None:
            return
        result = self._on_candle_finalized(candle)
        if inspect.isawaitable(result):
            await result


def execution_datetime(tick: DomesticExecutionTick) -> datetime:
    """Convert KIS's YYYYMMDD and HHMMSS execution fields into KST time."""

    try:
        parsed = datetime.strptime(
            f"{tick.business_date}{tick.execution_time.zfill(6)}", "%Y%m%d%H%M%S"
        )
    except ValueError as error:
        raise ValueError(
            f"Invalid KIS execution timestamp: {tick.business_date} {tick.execution_time}"
        ) from error
    return parsed.replace(tzinfo=KOREA_TIMEZONE)


def _minute_bucket(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _tick_identity(tick: DomesticExecutionTick) -> tuple[object, ...]:
    return (
        tick.stock_code,
        tick.business_date,
        tick.execution_time,
        tick.price,
        tick.execution_volume,
        tick.accumulated_volume,
    )
