from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException

from apps.worker.api import routes_news


class NewsEvidenceRouteTests(unittest.TestCase):
    def test_list_news_evidence_returns_recent_llm_rows(self) -> None:
        published_at = datetime(
            2026,
            8,
            27,
            9,
            30,
            tzinfo=timezone.utc,  # noqa: UP017 - study env runs Python 3.10.
        )

        def fake_fetch_one(sql: str, params: dict) -> dict | None:
            self.assertIn("dim_company", sql)
            self.assertEqual(params["corp_code"], "00126380")
            return {"stock_code": "005930", "corp_name": "삼성전자"}

        def fake_fetch_all(sql: str, params: dict) -> list[dict]:
            self.assertIn("sentiment_source = 'llm'", sql)
            self.assertEqual(params, {"corp_code": "00126380", "limit": 2})
            return [
                {
                    "title": "삼성전자 실적 전망 상향",
                    "url": "https://example.com/news",
                    "published_at": published_at,
                    "sentiment_score": 0.83,
                    "topic_tag": "실적 기대 변화가 투자자 관심에 영향을 줄 수 있습니다.",
                }
            ]

        with (
            patch.object(routes_news.entity_resolution, "resolve_by_name", return_value="00126380"),
            patch.object(routes_news.db, "fetch_one", side_effect=fake_fetch_one),
            patch.object(routes_news.db, "fetch_all", side_effect=fake_fetch_all),
        ):
            result = routes_news.list_news_evidence("005930", limit=2)

        self.assertEqual(result["stock_code"], "005930")
        self.assertEqual(result["corp_name"], "삼성전자")
        self.assertEqual(
            result["items"],
            [
                {
                    "title": "삼성전자 실적 전망 상향",
                    "url": "https://example.com/news",
                    "published_at": "2026-08-27T09:30:00+00:00",
                    "sentiment_score": 0.83,
                    "evidence": "실적 기대 변화가 투자자 관심에 영향을 줄 수 있습니다.",
                }
            ],
        )

    def test_list_news_evidence_raises_404_for_unknown_stock(self) -> None:
        with patch.object(routes_news.entity_resolution, "resolve_by_name", return_value=None):
            with self.assertRaises(HTTPException) as caught:
                routes_news.list_news_evidence("000000", limit=5)

        self.assertEqual(caught.exception.status_code, 404)

    def test_refresh_news_evidence_runs_news_pipeline(self) -> None:
        with (
            patch.object(routes_news.entity_resolution, "resolve_by_name", return_value="00126380"),
            patch.object(
                routes_news.db,
                "fetch_one",
                return_value={"stock_code": "005930", "corp_name": "삼성전자"},
            ),
            patch.object(
                routes_news.news_sentiment,
                "process_news_batch",
                return_value={
                    "corp_code": "00126380",
                    "collected": 3,
                    "saved": 2,
                    "high_impact": 1,
                    "rolling_score": 0.42,
                },
            ) as process_news_batch,
        ):
            result = routes_news.refresh_news_evidence("005930")

        process_news_batch.assert_called_once_with("00126380")
        self.assertEqual(result["stock_code"], "005930")
        self.assertEqual(result["corp_name"], "삼성전자")
        self.assertEqual(result["result"]["high_impact"], 1)


if __name__ == "__main__":
    unittest.main()
