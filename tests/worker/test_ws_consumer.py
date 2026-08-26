from __future__ import annotations

import asyncio
import json
import unittest
from collections import deque
from contextlib import AbstractAsyncContextManager
from decimal import Decimal

from apps.worker.ingestion.kis_client import KISSettings
from apps.worker.streaming.ws_consumer import (
    KIS_EXECUTION_FIELD_COUNT,
    KISWebSocketConsumer,
    build_subscription_message,
    is_ping_pong_message,
    parse_execution_message,
)


class FakeWebSocket:
    def __init__(self, received: list[object] | None = None) -> None:
        self._received = deque(received or [])
        self.sent: list[str] = []
        self.pongs: list[str | bytes] = []
        self.closed = False
        self.entered = asyncio.Event()

    async def __aenter__(self) -> "FakeWebSocket":
        self.entered.set()
        return self

    async def __aexit__(self, *_: object) -> None:
        self.closed = True

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str | bytes:
        if self._received:
            next_value = self._received.popleft()
            if isinstance(next_value, Exception):
                raise next_value
            return next_value  # type: ignore[return-value]
        while not self.closed:
            await asyncio.sleep(0.001)
        raise OSError("closed")

    async def pong(self, data: str | bytes = b"") -> None:
        self.pongs.append(data)

    async def close(self) -> None:
        self.closed = True


class FakeConnectionFactory:
    def __init__(self, connections: list[FakeWebSocket]) -> None:
        self.connections = deque(connections)
        self.urls: list[str] = []

    def __call__(self, url: str) -> AbstractAsyncContextManager[FakeWebSocket]:
        self.urls.append(url)
        return self.connections.popleft()


def execution_frame() -> str:
    values = [""] * KIS_EXECUTION_FIELD_COUNT
    values[0] = "005930"
    values[1] = "090003"
    values[2] = "72000"
    values[10] = "72100"
    values[11] = "71900"
    values[12] = "10"
    values[13] = "1000"
    values[33] = "20260823"
    return "0|H0STCNT0|1|" + "^".join(values)


class KISWebSocketConsumerTests(unittest.IsolatedAsyncioTestCase):
    def test_execution_frame_parses_official_field_positions(self) -> None:
        ticks = parse_execution_message(execution_frame())
        self.assertEqual(len(ticks), 1)
        tick = ticks[0]
        self.assertEqual(tick.stock_code, "005930")
        self.assertEqual(tick.price, Decimal("72000"))
        self.assertEqual(tick.execution_volume, 10)
        self.assertEqual(tick.accumulated_volume, 1000)

    def test_malformed_execution_frame_is_ignored(self) -> None:
        self.assertEqual(parse_execution_message("0|H0STCNT0|1|005930^090003"), ())

    def test_subscription_payload_uses_public_execution_tr_id(self) -> None:
        payload = json.loads(build_subscription_message("approval", "005930"))
        self.assertEqual(payload["header"]["tr_type"], "1")
        self.assertEqual(payload["body"]["input"], {"tr_id": "H0STCNT0", "tr_key": "005930"})

    def test_ping_pong_detection_handles_malformed_control_data(self) -> None:
        self.assertTrue(is_ping_pong_message('{"header":{"tr_id":"PINGPONG"}}'))
        self.assertFalse(is_ping_pong_message('{"header":null}'))

    async def test_reconnect_resubscribes_existing_symbol(self) -> None:
        first = FakeWebSocket([OSError("network down")])
        second = FakeWebSocket()
        factory = FakeConnectionFactory([first, second])

        async def approval_key() -> str:
            return "approval"

        consumer = KISWebSocketConsumer(
            KISSettings("key", "secret"),
            approval_key_provider=approval_key,
            connection_factory=factory,
            reconnect_initial_seconds=0.001,
            reconnect_max_seconds=0.002,
        )
        self.assertTrue(await consumer.subscribe("005930"))
        self.assertFalse(await consumer.subscribe("005930"))
        consumer.start()
        await asyncio.wait_for(second.entered.wait(), timeout=1)
        self.assertTrue(consumer.is_connected)
        await consumer.close()
        self.assertFalse(consumer.is_connected)

        self.assertEqual(len(first.sent), 1)
        self.assertEqual(len(second.sent), 1)
        self.assertEqual(json.loads(second.sent[0])["body"]["input"]["tr_key"], "005930")
