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


# --- 업종(섹터) 조회·매핑 ---
#
# corpCode.xml 은 업종 정보를 주지 않는다. company.json 의 induty_code(KSIC 표준산업분류
# 코드)를 dim_sector_sensitivity 에 이미 시딩해둔 업종 라벨로 매핑한다. 정밀한 5단위 매핑
# 표를 만들기보다, 상위 2~3자리 접두사 기준의 실용적 매핑으로 시작한다(길수록 우선 매치).
_INDUTY_SECTOR_BY_PREFIX_LEN: dict[int, dict[str, str]] = {
    3: {
        "264": "반도체",  # 반도체 소자/부품 제조업 (26 전자부품업의 세분류)
    },
    2: {
        "10": "음식료",
        "11": "음식료",
        "19": "화학",
        "20": "화학",
        "21": "제약/바이오",
        "22": "화학",
        "24": "철강",
        "25": "기계",
        "26": "전기전자",
        "27": "전기전자",
        "28": "전기전자",
        "29": "기계",
        "30": "자동차",
        "31": "조선",
        "35": "유틸리티",
        "41": "건설",
        "42": "건설",
        "45": "유통",
        "46": "유통",
        "47": "유통",
        "49": "운송",
        "50": "운송",
        "51": "운송",
        "52": "운송",
        "58": "게임",
        "61": "통신",
        "62": "IT서비스",
        "63": "IT서비스",
        "64": "은행",
        "65": "보험",
        "66": "증권",
    },
}


def map_induty_to_sector(induty_code: str | None) -> str | None:
    """KSIC induty_code -> dim_sector_sensitivity 업종 라벨. 매칭 없으면 None(결측 유지)."""
    if not induty_code:
        return None
    code = induty_code.strip()
    for prefix_len in sorted(_INDUTY_SECTOR_BY_PREFIX_LEN, reverse=True):
        sector = _INDUTY_SECTOR_BY_PREFIX_LEN[prefix_len].get(code[:prefix_len])
        if sector:
            return sector
    return None


@_retry_network
def fetch_company_info(corp_code: str) -> dict[str, Any] | None:
    """company.json — 기업 개황(업종코드 induty_code 포함) 조회."""
    params = {"crtfc_key": settings.dart_api_key, "corp_code": corp_code}
    with _client() as client:
        resp = client.get("/company.json", params=params)
        resp.raise_for_status()
        payload = resp.json()

    status = payload.get("status")
    if status == STATUS_NO_DATA:
        return None
    if status != STATUS_OK:
        raise DartApiError(f"company.json 조회 실패 (status={status}): {payload.get('message')}")
    return payload


def sync_sector(corp_code: str) -> str | None:
    """dim_company.sector 를 채운다. 업종은 사실상 불변이므로 이미 있으면 재조회하지 않는다."""
    existing = db.fetch_one(
        "SELECT sector FROM dim_company WHERE corp_code = :corp_code", {"corp_code": corp_code}
    )
    if existing and existing.get("sector"):
        return existing["sector"]

    try:
        info = fetch_company_info(corp_code)
    except Exception:
        log.exception("기업개황(업종) 조회 실패", corp_code=corp_code)
        return None
    if not info:
        return None

    sector = map_induty_to_sector(info.get("induty_code"))
    if sector:
        db.execute(
            "UPDATE dim_company SET sector = :sector WHERE corp_code = :corp_code",
            {"sector": sector, "corp_code": corp_code},
        )
    return sector


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
