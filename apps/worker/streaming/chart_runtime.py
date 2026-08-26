"""Bridge KIS streaming, candle aggregation, persistence, and chart API consumers."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Coroutine
from concurrent.futures import Future
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from apps.worker.ingestion.kis_client import KISClient, KISSettings, validate_stock_code
from apps.worker.pipeline.pattern_detection import annotate
from apps.worker.streaming.candle_aggregator import CandleAggregator, OHLCVCandle
from apps.worker.streaming.ws_consumer import DomesticExecutionTick, KISWebSocketConsumer

logger = logging.getLogger(__name__)

MAX_CHART_CANDLES = 300
MAX_CLIENT_QUEUE_SIZE = 100


class RealtimeChartRuntime:
    """Single-process chart runtime shared by watchlist routes and browser clients."""

    def __init__(self, settings: KISSettings, *, max_subscriptions: int = 3) -> None:
        self._settings = settings
        self._max_subscriptions = max_subscriptions
        self._client: KISClient | None = None
        self._consumer: KISWebSocketConsumer | None = None
        self._aggregator = CandleAggregator(on_candle_finalized=self._on_candle_finalized)
        self._history: dict[str, dict[datetime, OHLCVCandle]] = defaultdict(dict)
        self._annotations: dict[str, dict[datetime, list[dict[str, Any]]]] = defaultdict(dict)
        self._listeners: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._client = KISClient(self._settings)
        self._consumer = KISWebSocketConsumer(
            self._settings,
            approval_key_provider=self._client.get_websocket_approval_key,
            on_tick=self._on_tick,
        )

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.close()
        await self._aggregator.flush()
        if self._client is not None:
            await self._client.aclose()
        self._consumer = None
        self._client = None
        self._loop = None

    async def ensure_subscription(self, stock_code: str) -> bool:
        """Subscribe one watchlist symbol while enforcing the shared slot limit."""

        if self._consumer is None:
            raise RuntimeError("Realtime chart runtime has not started")
        code = validate_stock_code(stock_code)
        subscriptions = await self._consumer.get_subscriptions()
        if code not in subscriptions and len(subscriptions) >= self._max_subscriptions:
            logger.warning("KIS subscription denied: max watchlist slots reached")
            return False
        added = await self._consumer.subscribe(code)
        if not self._consumer.is_running:
            self._consumer.start()
        return added

    async def remove_subscription(self, stock_code: str) -> bool:
        if self._consumer is None:
            return False
        return await self._consumer.unsubscribe(stock_code)

    async def is_subscribed(self, stock_code: str) -> bool:
        if self._consumer is None:
            return False
        return validate_stock_code(stock_code) in await self._consumer.get_subscriptions()

    async def chart_candles(self, stock_code: str) -> list[dict[str, int | float]]:
        code = validate_stock_code(stock_code)
        async with self._lock:
            candles = sorted(self._history[code].values(), key=lambda candle: candle.timestamp)
        return [_chart_payload(candle) for candle in candles]

    async def chart_annotations(self, stock_code: str) -> list[dict[str, Any]]:
        """Return explanations detected since this worker started, in time order."""

        code = validate_stock_code(stock_code)
        async with self._lock:
            annotations = [
                annotation
                for entries in self._annotations[code].values()
                for annotation in entries
            ]
        return sorted(annotations, key=lambda annotation: annotation["ts"])

    async def add_listener(self, stock_code: str) -> asyncio.Queue[dict[str, Any]]:
        code = validate_stock_code(stock_code)
        queue: asyncio.Queue[dict[str, int | float]] = asyncio.Queue(MAX_CLIENT_QUEUE_SIZE)
        self._listeners[code].add(queue)
        return queue

    async def remove_listener(
        self, stock_code: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        code = validate_stock_code(stock_code)
        self._listeners[code].discard(queue)
        if not self._listeners[code]:
            self._listeners.pop(code, None)

    def subscribe_from_watchlist(self, stock_code: str) -> None:
        self._schedule(self.ensure_subscription(stock_code))

    def unsubscribe_from_watchlist(self, stock_code: str) -> None:
        self._schedule(self.remove_subscription(stock_code))

    def _schedule(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        if self._loop is None or not self._loop.is_running():
            coroutine.close()
            logger.warning("Ignoring watchlist event because realtime runtime is stopped")
            return
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        future.add_done_callback(_log_background_failure)

    async def _on_tick(self, tick: DomesticExecutionTick) -> None:
        await self._aggregator.ingest(tick)
        candle = await self._aggregator.current_candle(tick.stock_code)
        if candle is None:
            return
        await self._store_candle(candle)
        await self._publish(candle)

    async def _on_candle_finalized(self, candle: OHLCVCandle) -> None:
        await self._store_candle(candle)
        await self._persist_finalized_candle(candle)
        annotations = await self._detect_annotations(candle)
        if annotations:
            await self._persist_annotations(candle.stock_code, annotations)
            await self._publish_annotations(candle.stock_code, annotations)

    async def _store_candle(self, candle: OHLCVCandle) -> None:
        async with self._lock:
            history = self._history[candle.stock_code]
            history[candle.timestamp] = candle
            while len(history) > MAX_CHART_CANDLES:
                history.pop(min(history), None)

    async def _publish(self, candle: OHLCVCandle) -> None:
        payload = {"type": "candle", "candle": _chart_payload(candle)}
        for queue in tuple(self._listeners.get(candle.stock_code, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(payload)

    async def _detect_annotations(self, candle: OHLCVCandle) -> list[dict[str, Any]]:
        async with self._lock:
            history = sorted(self._history[candle.stock_code].values(), key=lambda item: item.timestamp)
        detected = annotate(candle.stock_code, [_pattern_row(item) for item in history])
        annotations = [
            _annotation_payload(annotation)
            for annotation in detected
            if annotation["ts"] == candle.timestamp
        ]
        async with self._lock:
            self._annotations[candle.stock_code][candle.timestamp] = annotations
        return annotations

    async def _publish_annotations(
        self, stock_code: str, annotations: list[dict[str, Any]]
    ) -> None:
        payload = {"type": "annotations", "annotations": annotations}
        for queue in tuple(self._listeners.get(stock_code, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(payload)

    async def _persist_finalized_candle(self, candle: OHLCVCandle) -> None:
        try:
            await asyncio.to_thread(_persist_candle, candle)
        except Exception:
            # Database outages must not interrupt the KIS consumer or browser feed.
            logger.warning("Could not persist finalized candle", exc_info=True)

    async def _persist_annotations(
        self, stock_code: str, annotations: list[dict[str, Any]]
    ) -> None:
        try:
            await asyncio.to_thread(_persist_annotations, stock_code, annotations)
        except Exception:
            # An explanation is supplementary; losing DB access must not stop quotes.
            logger.warning("Could not persist chart annotations", exc_info=True)


def _chart_payload(candle: OHLCVCandle) -> dict[str, int | float]:
    return {
        "time": int(candle.timestamp.timestamp()),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": candle.volume,
    }


def _pattern_row(candle: OHLCVCandle) -> dict[str, object]:
    return {
        "ts": candle.timestamp,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _annotation_payload(annotation: dict[str, Any]) -> dict[str, Any]:
    timestamp = annotation["ts"]
    if not isinstance(timestamp, datetime):
        raise TypeError("Pattern annotation timestamp must be a datetime")
    return {
        "ts": int(timestamp.timestamp()),
        "pattern_label": annotation["pattern_label"],
        "indicator_flags": annotation["indicator_flags"],
        "explanation_text": annotation["explanation_text"],
    }


def _persist_candle(candle: OHLCVCandle) -> None:
    from apps.worker.core import db

    db.execute(
        """
        INSERT INTO fact_ohlcv_realtime
            (stock_code, ts, open, high, low, close, volume, bid_price, ask_price)
        VALUES
            (:stock_code, :ts, :open, :high, :low, :close, :volume, :bid_price, :ask_price)
        ON CONFLICT (stock_code, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            bid_price = EXCLUDED.bid_price,
            ask_price = EXCLUDED.ask_price
        """,
        {
            "stock_code": candle.stock_code,
            "ts": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "bid_price": candle.bid_price,
            "ask_price": candle.ask_price,
        },
    )


def _persist_annotations(stock_code: str, annotations: list[dict[str, Any]]) -> None:
    from apps.worker.core import db

    db.execute(
        """
        INSERT INTO fact_chart_annotation
            (stock_code, ts, pattern_label, indicator_flags, explanation_text)
        VALUES
            (:stock_code, :ts, :pattern_label, CAST(:indicator_flags AS JSONB), :explanation_text)
        """,
        [
            {
                "stock_code": stock_code,
                "ts": datetime.fromtimestamp(annotation["ts"], tz=timezone.utc),
                "pattern_label": annotation["pattern_label"],
                "indicator_flags": json.dumps(annotation["indicator_flags"]),
                "explanation_text": annotation["explanation_text"],
            }
            for annotation in annotations
        ],
    )


def _log_background_failure(future: object) -> None:
    if not isinstance(future, Future):
        return
    try:
        future.result()
    except Exception:
        logger.warning("Watchlist subscription update failed", exc_info=True)
