from __future__ import annotations

import unittest

import httpx

from apps.worker.ingestion.kis_client import KISAPIError, KISClient, KISSettings


class KISClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_price_reuses_cached_token(self) -> None:
        calls = {"token": 0, "price": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/tokenP":
                calls["token"] += 1
                return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
            if request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price":
                calls["price"] += 1
                self.assertEqual(request.headers["authorization"], "Bearer test-token")
                self.assertEqual(request.headers["tr_id"], "FHKST01010100")
                self.assertEqual(request.url.params["FID_INPUT_ISCD"], "005930")
                return httpx.Response(200, json={"rt_cd": "0", "output": {"stck_prpr": "72000"}})
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = KISClient(KISSettings("key", "secret"), client=transport)
            self.assertEqual((await client.get_current_price("005930"))["stck_prpr"], "72000")
            await client.get_current_price("005930")

        self.assertEqual(calls, {"token": 1, "price": 2})

    async def test_expired_token_is_refreshed_once(self) -> None:
        tokens = iter(["old-token", "new-token"])
        price_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal price_calls
            if request.url.path == "/oauth2/tokenP":
                return httpx.Response(200, json={"access_token": next(tokens), "expires_in": 3600})
            price_calls += 1
            if price_calls == 1:
                return httpx.Response(200, json={"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "expired"})
            self.assertEqual(request.headers["authorization"], "Bearer new-token")
            return httpx.Response(200, json={"rt_cd": "0", "output": {"stck_prpr": "72100"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = KISClient(KISSettings("key", "secret"), client=transport)
            result = await client.get_current_price("005930")

        self.assertEqual(result["stck_prpr"], "72100")
        self.assertEqual(price_calls, 2)

    async def test_invalid_stock_code_does_not_call_kis(self) -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as transport:
            client = KISClient(KISSettings("key", "secret"), client=transport)
            with self.assertRaisesRegex(ValueError, "six-digit"):
                await client.get_current_price("INVALID")

    async def test_kis_error_is_exposed_without_response_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/oauth2/tokenP":
                return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})
            return httpx.Response(200, json={"rt_cd": "1", "msg_cd": "INVALID", "msg1": "invalid stock"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            client = KISClient(KISSettings("key", "secret"), client=transport)
            with self.assertRaises(KISAPIError) as caught:
                await client.get_current_price("005930")

        self.assertEqual(caught.exception.kis_code, "INVALID")
