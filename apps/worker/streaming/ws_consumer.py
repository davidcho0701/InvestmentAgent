"""KIS domestic-stock execution WebSocket subscription manager.

Only public market execution data (H0STCNT0) is consumed here.  This module
does not subscribe to customer execution notices and contains no order APIs.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import websockets

from apps.worker.ingestion.kis_client import (
    KISAPIError,
    KISAuthenticationError,
    KISClient,
    KISSettings,
    validate_stock_code,
)

logger = logging.getLogger(__name__)

LIVE_WEBSOCKET_URL = "ws://ops.koreainvestment.com:21000"
MOCK_WEBSOCKET_URL = "ws://ops.koreainvestment.com:31000"
DOMESTIC_EXECUTION_TR_ID = "H0STCNT0"
SUBSCRIBE_TR_TYPE = "1"
UNSUBSCRIBE_TR_TYPE = "2"
KIS_EXECUTION_FIELD_COUNT = 46

# KIS's official H0STCNT0 sample maps the data in this exact order.
KIS_DOMESTIC_EXECUTION_FIELDS = (
    "stock_code",
    "execution_time",
    "current_price",
    "price_change_sign",
    "price_change",
    "price_change_rate",
    "weighted_average_price",
    "open_price",
    "high_price",
    "low_price",
    "ask_price_1",
    "bid_price_1",
    "execution_volume",
    "accumulated_volume",
    "accumulated_turnover",
    "sell_execution_count",
    "buy_execution_count",
    "net_buy_execution_count",
    "execution_strength",
    "total_sell_quantity",
    "total_buy_quantity",
    "execution_classification",
    "buy_ratio",
    "previous_day_volume_change_rate",
    "open_time",
    "open_price_change_sign",
    "open_price_change",
    "high_time",
    "high_price_change_sign",
    "high_price_change",
    "low_time",
    "low_price_change_sign",
    "low_price_change",
    "business_date",
    "extended_operation_code",
    "trading_halt_yn",
    "ask_quantity_1",
    "bid_quantity_1",
    "total_ask_quantity",
    "total_bid_quantity",
    "volume_turnover_rate",
    "previous_same_time_accumulated_volume",
    "previous_same_time_accumulated_volume_rate",
    "time_classification_code",
    "arbitrary_termination_code",
    "static_vi_trigger_price",
)


class WebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...

    async def pong(self, data: str | bytes = b"") -> None: ...

    async def close(self) -> None: ...


ConnectionFactory = Callable[[str], AbstractAsyncContextManager[WebSocketConnection]]
ApprovalKeyProvider = Callable[[], Awaitable[str]]
TickHandler = Callable[["DomesticExecutionTick"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class DomesticExecutionTick:
    stock_code: str
    execution_time: str
    price: Decimal
    execution_volume: int
    accumulated_volume: int
    ask_price: Decimal | None
    bid_price: Decimal | None
    business_date: str


def websocket_url(settings: KISSettings) -> str:
    return MOCK_WEBSOCKET_URL if settings.is_mock else LIVE_WEBSOCKET_URL


def build_subscription_message(
    approval_key: str, stock_code: str, *, unsubscribe: bool = False
) -> str:
    """Build the KIS public domestic-execution subscribe/unsubscribe payload."""

    code = validate_stock_code(stock_code)
    return json.dumps(
        {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": UNSUBSCRIBE_TR_TYPE if unsubscribe else SUBSCRIBE_TR_TYPE,
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": DOMESTIC_EXECUTION_TR_ID, "tr_key": code}},
        },
        separators=(",", ":"),
    )


def parse_execution_message(message: str | bytes) -> tuple[DomesticExecutionTick, ...]:
    """Parse an H0STCNT0 data frame; malformed frames safely yield no ticks."""

    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Ignoring non-UTF-8 KIS WebSocket frame")
            return ()
    if not message.startswith(f"0|{DOMESTIC_EXECUTION_TR_ID}|"):
        return ()

    parts = message.split("|", maxsplit=3)
    if len(parts) != 4:
        logger.warning("Ignoring malformed KIS execution frame header")
        return ()
    try:
        count = int(parts[2])
    except ValueError:
        logger.warning("Ignoring KIS execution frame with invalid record count")
        return ()
    if count < 1:
        return ()

    values = parts[3].split("^")
    expected_value_count = count * KIS_EXECUTION_FIELD_COUNT
    if len(values) != expected_value_count:
        logger.warning(
            "Ignoring malformed KIS execution frame: expected %d fields, received %d",
            expected_value_count,
            len(values),
        )
        return ()

    ticks: list[DomesticExecutionTick] = []
    for offset in range(0, len(values), KIS_EXECUTION_FIELD_COUNT):
        record = values[offset : offset + KIS_EXECUTION_FIELD_COUNT]
        try:
            ticks.append(
                DomesticExecutionTick(
                    stock_code=validate_stock_code(record[0]),
                    execution_time=record[1],
                    price=_to_decimal(record[2]),
                    execution_volume=_to_int(record[12]),
                    accumulated_volume=_to_int(record[13]),
                    ask_price=_to_optional_decimal(record[10]),
                    bid_price=_to_optional_decimal(record[11]),
                    business_date=record[33],
                )
            )
        except (ValueError, InvalidOperation) as error:
            logger.warning("Ignoring malformed KIS execution record: %s", error)
    return tuple(ticks)


def is_ping_pong_message(message: str | bytes) -> bool:
    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError:
            return False
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    header = payload.get("header")
    return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"


def log_control_message(message: str | bytes) -> None:
    """Log KIS acknowledgement/errors without exposing approval credentials."""

    if isinstance(message, bytes):
        try:
            message = message.decode("utf-8")
        except UnicodeDecodeError:
            return
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring unrecognized KIS WebSocket message")
        return
    if not isinstance(payload, dict):
        logger.warning("Ignoring unexpected KIS WebSocket control message")
        return

    header = payload.get("header")
    body = payload.get("body")
    if not isinstance(header, dict) or not isinstance(body, dict):
        logger.warning("Ignoring malformed KIS WebSocket control message")
        return
    if body.get("rt_cd") in ("1", 1):
        logger.warning(
            "KIS WebSocket API error: tr_id=%s code=%s message=%s",
            header.get("tr_id", "unknown"),
            body.get("msg_cd", "unknown"),
            body.get("msg1", "unknown"),
        )
    else:
        logger.debug("KIS WebSocket acknowledgement: tr_id=%s", header.get("tr_id"))


class KISWebSocketConsumer:
    """Maintain one KIS connection and resubscribe desired symbols after reconnect."""

    def __init__(
        self,
        settings: KISSettings,
        *,
        approval_key_provider: ApprovalKeyProvider,
        on_tick: TickHandler | None = None,
        connection_factory: ConnectionFactory | None = None,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
    ) -> None:
        self._settings = settings
        self._approval_key_provider = approval_key_provider
        self._on_tick = on_tick
        self._connection_factory = connection_factory or _default_connection_factory
        self._reconnect_initial_seconds = reconnect_initial_seconds
        self._reconnect_max_seconds = reconnect_max_seconds
        self._subscriptions: set[str] = set()
        self._subscription_lock = asyncio.Lock()
        self._connection: WebSocketConnection | None = None
        self._approval_key: str | None = None
        self._stopped = asyncio.Event()
        self._run_task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._last_disconnect_kind: str | None = None
        self._last_close_code: int | None = None

    @property
    def is_running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    @property
    def is_connected(self) -> bool:
        """Whether the KIS connection is currently open and subscribed."""

        return self._connected.is_set()

    @property
    def last_disconnect_kind(self) -> str | None:
        """A safe, secret-free indication of the latest connection failure."""

        return self._last_disconnect_kind

    @property
    def last_close_code(self) -> int | None:
        """The WebSocket close code, if the most recent failure supplied one."""

        return self._last_close_code

    async def subscribe(self, stock_code: str) -> bool:
        """Add a symbol once and immediately subscribe when connected."""

        code = validate_stock_code(stock_code)
        async with self._subscription_lock:
            if code in self._subscriptions:
                logger.debug("KIS subscription already exists for %s", code)
                return False
            self._subscriptions.add(code)
            if self._connection and self._approval_key:
                await self._send_subscription_safely(code)
            logger.info("KIS subscription added: %s", code)
            return True

    async def unsubscribe(self, stock_code: str) -> bool:
        """Remove a desired symbol and send a KIS cancellation if connected."""

        code = validate_stock_code(stock_code)
        async with self._subscription_lock:
            if code not in self._subscriptions:
                return False
            self._subscriptions.remove(code)
            if self._connection and self._approval_key:
                await self._send_subscription_safely(code, unsubscribe=True)
            logger.info("KIS subscription removed: %s", code)
            return True

    async def get_subscriptions(self) -> tuple[str, ...]:
        async with self._subscription_lock:
            return tuple(sorted(self._subscriptions))

    def start(self) -> asyncio.Task[None]:
        """Start the reconnecting consumer in the current event loop."""

        if self.is_running:
            return self._run_task  # type: ignore[return-value]
        self._stopped.clear()
        self._run_task = asyncio.create_task(self.run_forever(), name="kis-websocket-consumer")
        return self._run_task

    async def reconnect(self) -> None:
        """Close the active connection; the background loop will resubscribe it."""

        if not self.is_running:
            self.start()
            return
        if self._connection is not None:
            logger.info("KIS WebSocket reconnect requested")
            await self._connection.close()

    async def close(self) -> None:
        """Gracefully stop receiving and retain no open KIS WebSocket."""

        self._stopped.set()
        if self._connection is not None:
            with suppress(Exception):
                await self._connection.close()
        if self._run_task is not None:
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self._run_task = None

    async def run_forever(self) -> None:
        """Connect, process frames, and retry with bounded exponential backoff."""

        delay = self._reconnect_initial_seconds
        while not self._stopped.is_set():
            try:
                await self._run_connection()
                delay = self._reconnect_initial_seconds
            except asyncio.CancelledError:
                raise
            except Exception as error:  # A disconnect must not crash the worker.
                self._last_disconnect_kind = type(error).__name__
                error_code = getattr(error, "code", None)
                self._last_close_code = error_code if isinstance(error_code, int) else None
                logger.warning(
                    "KIS WebSocket disconnected: %s%s",
                    type(error).__name__,
                    f" (code={self._last_close_code})" if self._last_close_code else "",
                )
            finally:
                self._connection = None
                self._approval_key = None
                self._connected.clear()

            if self._stopped.is_set():
                break
            logger.info("KIS WebSocket reconnect attempt in %.1f seconds", delay)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=delay)
            except TimeoutError:
                pass
            delay = min(delay * 2, self._reconnect_max_seconds)

    async def _run_connection(self) -> None:
        approval_key = await self._approval_key_provider()
        async with self._connection_factory(websocket_url(self._settings)) as connection:
            self._connection = connection
            self._approval_key = approval_key
            self._last_disconnect_kind = None
            self._last_close_code = None
            logger.info("KIS WebSocket connected")
            await self._resubscribe_all()
            self._connected.set()

            while not self._stopped.is_set():
                message = await connection.recv()
                if is_ping_pong_message(message):
                    await connection.pong(message)
                    continue
                ticks = parse_execution_message(message)
                if not ticks:
                    log_control_message(message)
                for tick in ticks:
                    logger.info(
                        "KIS execution received: stock=%s time=%s price=%s volume=%s",
                        tick.stock_code,
                        tick.execution_time,
                        tick.price,
                        tick.execution_volume,
                    )
                    await self._notify_tick(tick)

    async def _resubscribe_all(self) -> None:
        async with self._subscription_lock:
            for stock_code in sorted(self._subscriptions):
                await self._send_subscription(stock_code)

    async def _send_subscription(self, stock_code: str, *, unsubscribe: bool = False) -> None:
        if self._connection is None or self._approval_key is None:
            return
        message = build_subscription_message(
            self._approval_key, stock_code, unsubscribe=unsubscribe
        )
        await self._connection.send(message)

    async def _send_subscription_safely(
        self, stock_code: str, *, unsubscribe: bool = False
    ) -> None:
        try:
            await self._send_subscription(stock_code, unsubscribe=unsubscribe)
        except Exception as error:
            # The desired state remains stored and will be restored on reconnect.
            logger.warning(
                "KIS subscription command deferred for %s: %s",
                stock_code,
                type(error).__name__,
            )

    async def _notify_tick(self, tick: DomesticExecutionTick) -> None:
        if self._on_tick is None:
            return
        result = self._on_tick(tick)
        if inspect.isawaitable(result):
            await result


def _default_connection_factory(url: str) -> AbstractAsyncContextManager[WebSocketConnection]:
    # KIS's sample handles the JSON PINGPONG message itself, so library pings are off.
    return websockets.connect(url, ping_interval=None)  # type: ignore[return-value]


def _to_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _to_optional_decimal(value: str) -> Decimal | None:
    return _to_decimal(value) if value else None


def _to_int(value: str) -> int:
    return int(value.replace(",", ""))


async def _main() -> int:
    try:
        settings = KISSettings.from_env()
        stock_code = os.getenv("KIS_TEST_STOCK_CODE", "005930")
        async with KISClient(settings) as client:
            consumer = KISWebSocketConsumer(
                settings,
                approval_key_provider=client.get_websocket_approval_key,
            )
            await consumer.subscribe(stock_code)
            consumer.start()
            try:
                await asyncio.Event().wait()
            finally:
                await consumer.close()
    except KISAuthenticationError as error:
        logger.error("KIS WebSocket consumer is not configured: %s", error)
        return 2
    except KISAPIError as error:
        logger.error("KIS WebSocket setup failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        raise SystemExit(asyncio.run(_main()))
    except KeyboardInterrupt:
        logger.info("KIS WebSocket shutdown requested")
