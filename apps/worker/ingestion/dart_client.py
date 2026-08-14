"""DART OpenAPI 클라이언트 (Phase 1)."""
from __future__ import annotations

from typing import Any

import httpx

from ..core import get_logger, settings

log = get_logger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


def download_corp_codes() -> bytes:
    """corpCode.xml (zip) 다운로드. 반환값은 zip 바이트."""
    raise NotImplementedError("Phase 1")


def parse_corp_codes(zip_bytes: bytes) -> list[dict[str, Any]]:
    """zip -> [{corp_code, corp_name, stock_code}] 파싱."""
    raise NotImplementedError("Phase 1")


def upsert_companies(companies: list[dict[str, Any]]) -> int:
    """dim_company upsert. 상장사(stock_code 존재)만 대상."""
    raise NotImplementedError("Phase 1")


def fetch_financial_statement(
    corp_code: str, bsns_year: str, reprt_code: str = "11011", fs_div: str = "CFS"
) -> list[dict[str, Any]]:
    """fnlttSinglAcntAll.json — 단일회사 전체 재무제표.

    reprt_code: 11013(1분기) 11012(반기) 11014(3분기) 11011(사업보고서)
    fs_div: CFS(연결) | OFS(별도)
    """
    raise NotImplementedError("Phase 1")
