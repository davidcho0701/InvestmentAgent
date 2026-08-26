from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.worker.api.app import ChartLiteracyStore, RecentTickStore, render_dashboard
from apps.worker.streaming.candle_aggregator import OHLCVCandle
from apps.worker.streaming.ws_consumer import DomesticExecutionTick


class DashboardAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_recent_tick_store_formats_live_tick_for_json(self) -> None:
        store = RecentTickStore(max_items=2)
        await store.add(
            DomesticExecutionTick(
                stock_code="005930",
                execution_time="090003",
                price=Decimal("72000"),
                execution_volume=10,
                accumulated_volume=1000,
                ask_price=Decimal("72100"),
                bid_price=Decimal("71900"),
                business_date="20260825",
            )
        )

        self.assertEqual(
            await store.snapshot(),
            [
                {
                    "stock_code": "005930",
                    "executed_at": "2026-08-25 09:00:03",
                    "price": "72,000",
                    "execution_volume": 10,
                    "accumulated_volume": 1000,
                    "ask_price": "72,100",
                    "bid_price": "71,900",
                }
            ],
        )

    def test_dashboard_includes_chart_literacy_ui(self) -> None:
        page = render_dashboard()
        self.assertIn("InvestScope", page)
        self.assertIn("/api/dashboard", page)
        self.assertIn("투자 권유", page)
        self.assertIn("용어 사전", page)

    async def test_chart_literacy_store_adds_neutral_pattern_explanation(self) -> None:
        store = ChartLiteracyStore()
        start = datetime(2026, 8, 26, 9, 0, tzinfo=timezone(timedelta(hours=9)))
        for minute in range(20):
            await store.add_finalized_candle(
                OHLCVCandle(
                    stock_code="005930",
                    timestamp=start + timedelta(minutes=minute),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.1"),
                    volume=10,
                    bid_price=None,
                    ask_price=None,
                )
            )
        await store.add_finalized_candle(
            OHLCVCandle(
                stock_code="005930",
                timestamp=start + timedelta(minutes=20),
                open=Decimal("100"),
                high=Decimal("115"),
                low=Decimal("99"),
                close=Decimal("114"),
                volume=30,
                bid_price=None,
                ask_price=None,
            )
        )

        _, annotations = await store.snapshot()

        self.assertTrue(annotations)
        self.assertTrue(
            all("투자 신호가 아닙니다" in item["explanation_text"] for item in annotations)
        )


if __name__ == "__main__":
    unittest.main()
