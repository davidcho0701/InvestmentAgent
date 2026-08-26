from __future__ import annotations

import unittest
from decimal import Decimal

from apps.worker.streaming.candle_aggregator import CandleAggregator
from apps.worker.streaming.ws_consumer import DomesticExecutionTick


def tick(
    execution_time: str,
    price: str,
    *,
    stock_code: str = "005930",
    execution_volume: int = 1,
    accumulated_volume: int = 1,
    business_date: str = "20260826",
) -> DomesticExecutionTick:
    return DomesticExecutionTick(
        stock_code=stock_code,
        execution_time=execution_time,
        price=Decimal(price),
        execution_volume=execution_volume,
        accumulated_volume=accumulated_volume,
        ask_price=Decimal(price) + 100,
        bid_price=Decimal(price) - 100,
        business_date=business_date,
    )


class CandleAggregatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_minute_ohlcv_and_rollover(self) -> None:
        aggregator = CandleAggregator()
        await aggregator.ingest(tick("090003", "72000", execution_volume=10, accumulated_volume=10))
        await aggregator.ingest(tick("090010", "72100", execution_volume=20, accumulated_volume=30))
        await aggregator.ingest(tick("090025", "71900", execution_volume=30, accumulated_volume=60))
        await aggregator.ingest(tick("090058", "72200", execution_volume=40, accumulated_volume=100))

        current = await aggregator.current_candle("005930")
        self.assertIsNotNone(current)
        self.assertEqual((current.open, current.high, current.low, current.close), (Decimal("72000"), Decimal("72200"), Decimal("71900"), Decimal("72200")))
        self.assertEqual(current.volume, 100)

        finalized = await aggregator.ingest(tick("090101", "72300", execution_volume=50, accumulated_volume=150))
        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.timestamp.strftime("%H:%M"), "09:00")
        self.assertEqual(finalized.close, Decimal("72200"))
        self.assertEqual(finalized.volume, 100)

    async def test_interleaved_symbols_do_not_mix_candle_state(self) -> None:
        aggregator = CandleAggregator()
        await aggregator.ingest(tick("090003", "72000", stock_code="005930", execution_volume=10))
        await aggregator.ingest(tick("090005", "180000", stock_code="000660", execution_volume=20))
        finalized = await aggregator.ingest(tick("090101", "72100", stock_code="005930", execution_volume=30))

        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.stock_code, "005930")
        other = await aggregator.current_candle("000660")
        self.assertIsNotNone(other)
        self.assertEqual(other.open, Decimal("180000"))
        self.assertEqual(other.volume, 20)

    async def test_duplicate_execution_does_not_inflate_volume(self) -> None:
        aggregator = CandleAggregator()
        duplicate = tick("090003", "72000", execution_volume=10, accumulated_volume=10)
        await aggregator.ingest(duplicate)
        await aggregator.ingest(duplicate)
        finalized = await aggregator.ingest(tick("090101", "72100", execution_volume=20, accumulated_volume=30))

        self.assertIsNotNone(finalized)
        self.assertEqual(finalized.volume, 10)

    async def test_out_of_order_execution_preserves_chronological_open_and_close(self) -> None:
        aggregator = CandleAggregator()
        await aggregator.ingest(tick("090025", "71900", execution_volume=10, accumulated_volume=30))
        await aggregator.ingest(tick("090010", "72100", execution_volume=10, accumulated_volume=20))
        current = await aggregator.current_candle("005930")

        self.assertIsNotNone(current)
        self.assertEqual(current.open, Decimal("72100"))
        self.assertEqual(current.close, Decimal("71900"))
        self.assertEqual(current.volume, 20)

    async def test_finalized_candle_notifies_pipeline_callback(self) -> None:
        received = []

        async def on_finalized(candle) -> None:
            received.append(candle)

        aggregator = CandleAggregator(on_candle_finalized=on_finalized)
        await aggregator.ingest(tick("090003", "72000"))
        await aggregator.ingest(tick("090101", "72100"))

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].stock_code, "005930")
