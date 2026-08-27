from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from apps.worker.pipeline import news_sentiment


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    requests: list[dict] = []
    response_payload: dict = {}

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(
        self,
        url: str,
        *,
        headers: dict | None = None,
        json: dict | None = None,
    ) -> _FakeResponse:
        self.requests.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(self.response_payload)


class NewsSentimentLLMTests(unittest.TestCase):
    def tearDown(self) -> None:
        _FakeClient.requests = []
        _FakeClient.response_payload = {}

    def test_ollama_provider_uses_local_generate_api_without_api_key(self) -> None:
        _FakeClient.response_payload = {"response": "실적 전망 변화가 투자자 관심에 영향을 줍니다."}
        settings = SimpleNamespace(
            llm_provider="ollama",
            llm_api_key="",
            llm_model="qwen2.5:1.5b-instruct",
            ollama_base_url="http://localhost:11434",
        )

        with (
            patch.object(news_sentiment, "settings", settings),
            patch.object(news_sentiment.httpx, "Client", _FakeClient),
        ):
            result = news_sentiment.generate_evidence_with_llm("제목", "본문")

        self.assertEqual(result, "실적 전망 변화가 투자자 관심에 영향을 줍니다.")
        self.assertEqual(len(_FakeClient.requests), 1)
        request = _FakeClient.requests[0]
        self.assertEqual(request["url"], "http://localhost:11434/api/generate")
        self.assertIsNone(request["headers"])
        self.assertEqual(request["json"]["model"], "qwen2.5:1.5b-instruct")
        self.assertEqual(request["json"]["stream"], False)
        self.assertIn("매수/매도 권유 표현은 쓰지 마세요", request["json"]["prompt"])

    def test_anthropic_provider_requires_api_key(self) -> None:
        settings = SimpleNamespace(
            llm_provider="anthropic",
            llm_api_key="",
            llm_model="claude-haiku-4-5-20251001",
            ollama_base_url="http://localhost:11434",
        )

        with (
            patch.object(news_sentiment, "settings", settings),
            patch.object(news_sentiment.httpx, "Client", _FakeClient),
        ):
            result = news_sentiment.generate_evidence_with_llm("제목", "본문")

        self.assertEqual(result, "")
        self.assertEqual(_FakeClient.requests, [])

    def test_anthropic_provider_extracts_content_text(self) -> None:
        _FakeClient.response_payload = {
            "content": [
                {"type": "text", "text": "수익성 변화가 실적 기대에 영향을 줄 수 있습니다."}
            ]
        }
        settings = SimpleNamespace(
            llm_provider="anthropic",
            llm_api_key="test-key",
            llm_model="claude-haiku-4-5-20251001",
            ollama_base_url="http://localhost:11434",
        )

        with (
            patch.object(news_sentiment, "settings", settings),
            patch.object(news_sentiment.httpx, "Client", _FakeClient),
        ):
            result = news_sentiment.generate_evidence_with_llm("제목", "본문")

        self.assertEqual(result, "수익성 변화가 실적 기대에 영향을 줄 수 있습니다.")
        request = _FakeClient.requests[0]
        self.assertEqual(request["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(request["headers"]["x-api-key"], "test-key")
        self.assertEqual(request["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(request["json"]["model"], "claude-haiku-4-5-20251001")

    def test_ollama_http_error_returns_empty_string(self) -> None:
        class FailingClient(_FakeClient):
            def post(
                self,
                url: str,
                *,
                headers: dict | None = None,
                json: dict | None = None,
            ) -> _FakeResponse:
                raise httpx.ConnectError("connection failed")

        settings = SimpleNamespace(
            llm_provider="ollama",
            llm_api_key="",
            llm_model="qwen2.5:1.5b-instruct",
            ollama_base_url="http://localhost:11434/",
        )

        with (
            patch.object(news_sentiment, "settings", settings),
            patch.object(news_sentiment.httpx, "Client", FailingClient),
        ):
            result = news_sentiment.generate_evidence_with_llm("제목", "본문")

        self.assertEqual(result, "")
