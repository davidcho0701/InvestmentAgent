"""DART OpenAPI 클라이언트 (Phase 1)."""
from __future__ import annotations

import io
import zipfile
from typing import Any
from xml.etree import ElementTree

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..core import db, get_logger, settings

log = get_logger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"

# 조회된 데이터가 없음(정상적인 "결측", 에러 아님) — fnlttSinglAcntAll 등에서 흔함
STATUS_NO_DATA = "013"
STATUS_OK = "000"

_retry_network = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)


class DartApiError(RuntimeError):
    """status != '000'(정상) / '013'(데이터 없음) 인 DART 응답."""


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@_retry_network
def download_corp_codes() -> bytes:
    """corpCode.xml (zip) 다운로드. 반환값은 zip 바이트."""
    with _client() as client:
        resp = client.get("/corpCode.xml", params={"crtfc_key": settings.dart_api_key})
        resp.raise_for_status()
        content = resp.content

    # 인증 실패 등 에러 시 DART 는 zip 대신 XML 에러 응답을 준다.
    if not content.startswith(b"PK"):
        try:
            root = ElementTree.fromstring(content)
            status = root.findtext("status") or "unknown"
            message = root.findtext("message") or content[:200].decode("utf-8", "replace")
        except ElementTree.ParseError:
            status, message = "unknown", content[:200].decode("utf-8", "replace")
        raise DartApiError(f"corpCode.xml 다운로드 실패 (status={status}): {message}")

    return content


def parse_corp_codes(zip_bytes: bytes) -> list[dict[str, Any]]:
    """zip -> [{corp_code, corp_name, stock_code}] 파싱."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    root = ElementTree.fromstring(xml_bytes)
    companies: list[dict[str, Any]] = []
    for node in root.iter("list"):
        corp_code = (node.findtext("corp_code") or "").strip()
        corp_name = (node.findtext("corp_name") or "").strip()
        stock_code = (node.findtext("stock_code") or "").strip()
        if not corp_code:
            continue
        companies.append(
            {
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code or None,
            }
        )
    return companies


def upsert_companies(companies: list[dict[str, Any]]) -> int:
    """dim_company upsert. 상장사(stock_code 존재)만 대상."""
    listed = [c for c in companies if c.get("stock_code")]
    if not listed:
        return 0

    sql = """
        INSERT INTO dim_company (corp_code, stock_code, corp_name)
        VALUES (:corp_code, :stock_code, :corp_name)
        ON CONFLICT (corp_code) DO UPDATE
        SET stock_code = EXCLUDED.stock_code,
            corp_name  = EXCLUDED.corp_name
    """
    db.execute(sql, listed)
    return len(listed)


@_retry_network
def fetch_financial_statement(
    corp_code: str, bsns_year: str, reprt_code: str = "11011", fs_div: str = "CFS"
) -> list[dict[str, Any]]:
    """fnlttSinglAcntAll.json — 단일회사 전체 재무제표.

    reprt_code: 11013(1분기) 11012(반기) 11014(3분기) 11011(사업보고서)
    fs_div: CFS(연결) | OFS(별도)
    """
    params = {
        "crtfc_key": settings.dart_api_key,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div,
    }
    with _client() as client:
        resp = client.get("/fnlttSinglAcntAll.json", params=params)
        resp.raise_for_status()
        payload = resp.json()

    status = payload.get("status")
    if status == STATUS_NO_DATA:
        log.info(
            "재무제표 데이터 없음",
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            fs_div=fs_div,
        )
        return []
    if status != STATUS_OK:
        raise DartApiError(
            f"fnlttSinglAcntAll 조회 실패 (status={status}): {payload.get('message')}"
        )

    return payload.get("list", [])
