"""Small, read-only KIS Developers REST client.

This module deliberately contains market-data endpoints only.  It does not
expose any order, buy, or sell API.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

LIVE_API_BASE_URL = "https://openapi.koreainvestment.com:9443"
MOCK_API_BASE_URL = "https://openapivts.koreainvestment.com:29443"
TOKEN_PATH = "/oauth2/tokenP"
WEBSOCKET_APPROVAL_PATH = "/oauth2/Approval"
CURRENT_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
CURRENT_PRICE_TR_ID = "FHKST01010100"
TOKEN_EXPIRY_SAFETY_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 10.0


class KISAPIError(RuntimeError):
    """A transport or KIS response error that is safe to log."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        kis_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.kis_code = kis_code


class KISAuthenticationError(KISAPIError):
    """KIS could not issue a REST token or a WebSocket approval key."""


# Backward-compatible name used by the existing analytics pipeline.  The
# pipeline's analyst-consensus endpoint remains deliberately unimplemented
# until its KIS TR ID and response schema have been live-verified.
KisApiError = KISAPIError


@dataclass(frozen=True, slots=True)
class KISSettings:
    """KIS configuration loaded from environment variables."""

    app_key: str
    app_secret: str
    is_mock: bool = False

    @property
    def api_base_url(self) -> str:
        return MOCK_API_BASE_URL if self.is_mock else LIVE_API_BASE_URL

    @classmethod
    def from_env(cls) -> "KISSettings":
        # `override=False` leaves credentials injected by a deployment intact.
        load_dotenv(override=False)
        app_key = os.getenv("KIS_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        raw_is_mock = os.getenv("KIS_IS_MOCK", "false").strip().lower()
        is_mock = raw_is_mock in {"1", "true", "yes", "on"}

        missing = [
            name
            for name, value in (("KIS_APP_KEY", app_key), ("KIS_APP_SECRET", app_secret))
            if not value
        ]
        if missing:
            raise KISAuthenticationError(
                "Missing required KIS environment variable(s): " + ", ".join(missing)
            )
        return cls(app_key=app_key, app_secret=app_secret, is_mock=is_mock)


@dataclass(slots=True)
class _CachedToken:
    value: str
    expires_at: float

    def is_usable(self) -> bool:
        return time.monotonic() < self.expires_at


def validate_stock_code(stock_code: str) -> str:
    """Validate the domestic six-digit stock code expected by this client."""

    normalized = stock_code.strip()
    if len(normalized) != 6 or not normalized.isdecimal():
        raise ValueError("stock_code must be a six-digit domestic stock code, e.g. '005930'")
    return normalized


class KISClient:
    """Async KIS REST client with token reuse and one-time auth retry."""

    def __init__(
        self,
        settings: KISSettings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._token: _CachedToken | None = None
        self._token_lock = asyncio.Lock()

    @classmethod
    def from_env(cls) -> "KISClient":
        return cls(KISSettings.from_env())

    async def __aenter__(self) -> "KISClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        """Issue or reuse a KIS REST token without logging its value."""

        async with self._token_lock:
            if not force_refresh and self._token and self._token.is_usable():
                return self._token.value

            payload = {
                "grant_type": "client_credentials",
                "appkey": self.settings.app_key,
                "appsecret": self.settings.app_secret,
            }
            response = await self._request_json("POST", TOKEN_PATH, json=payload)
            access_token = response.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise KISAuthenticationError(
                    "KIS token response did not include access_token",
                    kis_code=_string_value(response.get("msg_cd")),
                )

            expires_in = _positive_int(response.get("expires_in"), default=0)
            expires_at = time.monotonic() + max(
                0, expires_in - TOKEN_EXPIRY_SAFETY_SECONDS
            )
            self._token = _CachedToken(value=access_token, expires_at=expires_at)
            logger.info("KIS token acquired")
            return access_token

    async def get_websocket_approval_key(self) -> str:
        """Issue the KIS approval key required for a WebSocket connection."""

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.app_key,
            # KIS's Approval endpoint uses `secretkey`, unlike tokenP.
            "secretkey": self.settings.app_secret,
        }
        response = await self._request_json("POST", WEBSOCKET_APPROVAL_PATH, json=payload)
        approval_key = response.get("approval_key")
        if not isinstance(approval_key, str) or not approval_key:
            raise KISAuthenticationError(
                "KIS Approval response did not include approval_key",
                kis_code=_string_value(response.get("msg_cd")),
            )
        return approval_key

    async def get_current_price(self, stock_code: str) -> dict[str, Any]:
        """Return the KIS current-price output for one domestic stock."""

        code = validate_stock_code(stock_code)
        response = await self._authorized_request(
            "GET",
            CURRENT_PRICE_PATH,
            headers={"tr_id": CURRENT_PRICE_TR_ID},
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
            },
        )
        output = response.get("output")
        if not isinstance(output, dict):
            raise KISAPIError(
                "KIS current-price response did not include an output object",
                kis_code=_string_value(response.get("msg_cd")),
            )
        return output

    async def _authorized_request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str],
    ) -> dict[str, Any]:
        for attempt in range(2):
            token = await self.get_access_token(force_refresh=attempt == 1)
            request_headers = {
                "authorization": f"Bearer {token}",
                "appkey": self.settings.app_key,
                "appsecret": self.settings.app_secret,
                "content-type": "application/json",
                **headers,
            }
            try:
                return await self._request_json(
                    method, path, headers=request_headers, params=params
                )
            except KISAPIError as error:
                if attempt == 0 and _is_expired_token_error(error):
                    self._token = None
                    logger.info("KIS token expired; refreshing token")
                    continue
                raise
        raise AssertionError("unreachable")

    async def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.settings.api_base_url}{path}"
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as error:
            logger.warning("KIS API timeout for %s", path)
            raise KISAPIError("KIS API request timed out") from error
        except httpx.HTTPError as error:
            logger.warning("KIS API network error for %s: %s", path, type(error).__name__)
            raise KISAPIError("KIS API network request failed") from error

        try:
            payload = response.json()
        except ValueError as error:
            logger.warning("KIS API returned a non-JSON response for %s", path)
            raise KISAPIError(
                "KIS API returned an invalid JSON response", status_code=response.status_code
            ) from error
        if not isinstance(payload, dict):
            raise KISAPIError(
                "KIS API returned an unexpected JSON response",
                status_code=response.status_code,
            )

        if response.is_error or payload.get("rt_cd") not in (None, "0", 0):
            kis_code = _string_value(payload.get("msg_cd"))
            message = _string_value(payload.get("msg1")) or "KIS API request failed"
            logger.warning(
                "KIS API error for %s: status=%s code=%s",
                path,
                response.status_code,
                kis_code or "unknown",
            )
            raise KISAPIError(
                message,
                status_code=response.status_code,
                kis_code=kis_code,
            )
        return payload


def _positive_int(value: object, *, default: int) -> int:
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return default


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_expired_token_error(error: KISAPIError) -> bool:
    # EGW00123 is the token-expiry code shown in KIS's official sample.
    return error.status_code == 401 or error.kis_code == "EGW00123"


def fetch_analyst_consensus(stock_code: str) -> list[dict[str, Any]]:
    """Compatibility hook for Part 1; requires KIS schema verification first."""

    validate_stock_code(stock_code)
    raise NotImplementedError(
        "KIS analyst-consensus schema has not been live-verified; no request was sent."
    )


def fetch_daily_ohlcv(
    stock_code: str, start_date: str, end_date: str
) -> list[dict[str, Any]]:
    """Reserved for static charts once its exact KIS historical schema is verified."""

    validate_stock_code(stock_code)
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")
    raise NotImplementedError(
        "KIS historical OHLCV schema has not been live-verified; no request was sent."
    )


async def _main() -> int:
    try:
        stock_code = os.getenv("KIS_TEST_STOCK_CODE", "005930")
        async with KISClient.from_env() as client:
            price = await client.get_current_price(stock_code)
            logger.info(
                "KIS current price received for %s: %s",
                stock_code,
                price.get("stck_prpr", "unavailable"),
            )
    except KISAuthenticationError as error:
        logger.error("KIS REST client is not configured: %s", error)
        return 2
    except KISAPIError as error:
        logger.error("KIS REST request failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(asyncio.run(_main()))
