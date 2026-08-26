from __future__ import annotations

import unittest
from decimal import Decimal

from apps.worker.api.app import RecentTickStore, render_dashboard
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

    def test_dashboard_includes_live_monitor_ui(self) -> None:
        page = render_dashboard()
        self.assertIn("InvestScope", page)
        self.assertIn("/api/dashboard", page)
        self.assertIn("투자 권유", page)
