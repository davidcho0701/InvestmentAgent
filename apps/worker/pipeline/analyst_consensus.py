"""애널리스트 컨센서스 집계 (§3.2.7, Phase 3).

제약(§7): 이 값은 final_score 연산에 절대 섞지 않고, 별도 패널로만 노출한다.
"""

from __future__ import annotations

from typing import Any

from ..core import db, get_logger

log = get_logger(__name__)


def sync_consensus(stock_code: str) -> int:
    """KIS 투자의견 조회 -> fact_analyst_consensus 적재."""
    from ..ingestion import kis_client

    try:
        rows = kis_client.fetch_analyst_consensus(stock_code)
    except kis_client.KISAPIError as exc:
        log.warning(
            "KIS 투자의견 조회 실패",
            stock_code=stock_code,
            error_type=type(exc).__name__,
            status_code=exc.status_code,
            kis_code=exc.kis_code,
        )
        return 0
    except Exception:
        log.warning(
            "KIS 투자의견 조회 실패",
            stock_code=stock_code,
            error_type="unexpected",
        )
        return 0
    if not rows:
        return 0

    payload = [
        {
            "stock_code": r["stock_code"],
            "report_date": r.get("report_date"),
            "securities_firm": r.get("securities_firm"),
            "opinion": r.get("opinion"),
            "target_price": r.get("target_price"),
        }
        for r in rows
        if r.get("report_date")
    ]
    if not payload:
        return 0

    inserted = db.execute(
        """
        INSERT INTO fact_analyst_consensus
            (stock_code, report_date, securities_firm, opinion, target_price)
        VALUES
            (:stock_code, :report_date, :securities_firm, :opinion, :target_price)
        ON CONFLICT DO NOTHING
        """,
        payload,
    )
    return inserted


def summarize_consensus(stock_code: str, days: int = 90) -> dict[str, Any]:
    """최근 N일 의견 분포 + 평균 목표주가 요약 (프론트 패널용)."""
    rows = db.fetch_all(
        """
        SELECT opinion, target_price, report_date
        FROM fact_analyst_consensus
        WHERE stock_code = :stock_code
          AND report_date >= CURRENT_DATE - (:days || ' days')::interval
        ORDER BY report_date DESC
        """,
        {"stock_code": stock_code, "days": days},
    )

    if not rows:
        return {
            "opinion_counts": {},
            "avg_target_price": None,
            "report_count": 0,
            "latest_report_date": None,
        }

    opinion_counts: dict[str, int] = {}
    target_prices: list[float] = []
    for row in rows:
        if row.get("opinion"):
            opinion_counts[row["opinion"]] = opinion_counts.get(row["opinion"], 0) + 1
        if row.get("target_price") is not None:
            target_prices.append(row["target_price"])

    avg_target_price = sum(target_prices) / len(target_prices) if target_prices else None
    latest_report_date = rows[0]["report_date"]

    return {
        "opinion_counts": opinion_counts,
        "avg_target_price": avg_target_price,
        "report_count": len(rows),
        "latest_report_date": latest_report_date.isoformat() if latest_report_date else None,
    }
