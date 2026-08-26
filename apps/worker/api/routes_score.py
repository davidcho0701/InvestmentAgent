"""GET /api/score/{stock_code} — 관심종목 여부에 따라 라이브/스냅샷 자동 분기 (Phase 4)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..core import db, get_logger
from ..pipeline import analyst_consensus, entity_resolution, scoring

log = get_logger(__name__)

router = APIRouter(prefix="/api/score", tags=["score"])


@router.get("/{stock_code}")
def get_score(stock_code: str, user_id: str = Query(..., description="사용자 식별자")) -> dict:
    """관심종목이면 mart_investment_score(라이브), 아니면 스냅샷 캐시/재계산.

    스냅샷 응답에는 반드시 기준 시각(as_of)을 포함해 실시간과 혼동되지 않게 한다.
    애널리스트 컨센서스는 final_score 산식과 무관한 별도 필드로만 붙는다.
    """
    corp_code = entity_resolution.resolve_by_name(stock_code)
    if not corp_code:
        raise HTTPException(status_code=404, detail="등록되지 않은 종목입니다.")

    company = db.fetch_one(
        "SELECT stock_code, corp_name FROM dim_company WHERE corp_code = :corp_code",
        {"corp_code": corp_code},
    )
    watchlisted = db.fetch_one(
        "SELECT 1 FROM user_watchlist WHERE user_id = :user_id AND corp_code = :corp_code",
        {"user_id": user_id, "corp_code": corp_code},
    )

    if watchlisted:
        row = db.fetch_one(
            """
            SELECT final_score, contributing_factors, recommendation_label, score_date
            FROM mart_investment_score
            WHERE corp_code = :corp_code
            ORDER BY score_date DESC
            LIMIT 1
            """,
            {"corp_code": corp_code},
        )
        if not row:
            # 관심종목으로 갓 등록되어 아직 배치/이벤트 재계산이 한 번도 안 돈 경우 — 즉시 1회 계산.
            result = scoring.rescore_live(corp_code, trigger_type="event")
            response = {
                "final_score": result["final_score"],
                "mode": "live",
                "as_of": result["as_of"],
                "contributing_factors": result["contributing_factors"],
                "evidence": scoring.build_evidence_sentences(result["contributing_factors"]),
                "recommendation_label": result["recommendation_label"],
            }
        else:
            response = {
                "final_score": row["final_score"],
                "mode": "live",
                "as_of": row["score_date"].isoformat() if row["score_date"] else None,
                "contributing_factors": row["contributing_factors"],
                "evidence": scoring.build_evidence_sentences(row["contributing_factors"]),
                "recommendation_label": row["recommendation_label"],
            }
    else:
        try:
            response = scoring.compute_snapshot_and_cache(stock_code)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    response["stock_code"] = company["stock_code"] if company else stock_code
    response["corp_name"] = company["corp_name"] if company else None
    try:
        response["analyst_consensus"] = analyst_consensus.summarize_consensus(
            response["stock_code"]
        )
    except Exception:
        log.exception("애널리스트 컨센서스 조회 실패", stock_code=stock_code)
        response["analyst_consensus"] = None

    return response
