"""APScheduler 잡 등록.

실행: python -m apps.worker.scheduler.jobs  (리포 루트에서)
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..core import get_logger, settings

log = get_logger(__name__)


# --- 잡 본문 (각 Phase 에서 채운다) ---

def job_sync_corp_codes() -> None:
    """DART 기업코드 마스터 동기화 (주 1회)."""
    from ..ingestion import dart_client

    raw = dart_client.download_corp_codes()
    companies = dart_client.parse_corp_codes(raw)
    count = dart_client.upsert_companies(companies)
    log.info("기업코드 동기화 완료", count=count)


def job_sync_financials() -> None:
    """관심종목 + 파일럿 기업 재무제표 일 배치 (Phase 1)."""
    from ..core import db
    from ..pipeline import entity_resolution, financial_normalize

    pilot_stock_codes = list(entity_resolution.PILOT_ALIASES.keys())
    rows = db.fetch_all(
        """
        SELECT DISTINCT c.corp_code
        FROM dim_company c
        LEFT JOIN user_watchlist w ON w.corp_code = c.corp_code
        WHERE w.corp_code IS NOT NULL OR c.stock_code = ANY(:pilot_codes)
        """,
        {"pilot_codes": pilot_stock_codes},
    )
    corp_codes = [r["corp_code"] for r in rows]
    report_date = financial_normalize.latest_available_report_date()

    ok, empty, failed = 0, 0, 0
    for corp_code in corp_codes:
        try:
            features = financial_normalize.build_financial_features(corp_code, report_date)
            if not features:
                empty += 1
                continue
            financial_normalize.save_financial_statement(corp_code, report_date, features)
            ok += 1
        except Exception:
            log.exception("재무제표 동기화 실패", corp_code=corp_code)
            failed += 1

    log.info(
        "재무제표 일 배치 완료",
        report_date=report_date,
        ok=ok,
        empty=empty,
        failed=failed,
        total=len(corp_codes),
    )


def job_poll_news() -> None:
    """관심종목 뉴스 폴링 (NEWS_POLL_INTERVAL_MINUTES 주기, Phase 2)."""
    from ..core import db
    from ..pipeline import news_sentiment

    rows = db.fetch_all("SELECT DISTINCT corp_code FROM user_watchlist")
    for row in rows:
        try:
            result = news_sentiment.process_news_batch(row["corp_code"])
            log.info("뉴스 폴링 완료", **result)
        except Exception:
            log.exception("뉴스 폴링 실패", corp_code=row["corp_code"])


def job_sync_macro() -> None:
    """ECOS 거시지표 월 배치 (Phase 3)."""
    from ..ingestion import ecos_client

    count = ecos_client.sync_all_indicators()
    log.info("거시지표 동기화 완료", count=count)


def job_sync_consensus() -> None:
    """애널리스트 컨센서스 일 배치 (Phase 3)."""
    from ..core import db
    from ..pipeline import analyst_consensus

    rows = db.fetch_all(
        """
        SELECT DISTINCT c.stock_code
        FROM dim_company c
        JOIN user_watchlist w ON w.corp_code = c.corp_code
        WHERE c.stock_code IS NOT NULL
        """
    )
    total = 0
    for row in rows:
        try:
            total += analyst_consensus.sync_consensus(row["stock_code"])
        except Exception:
            log.exception("컨센서스 동기화 실패", stock_code=row["stock_code"])
    log.info("애널리스트 컨센서스 배치 완료", count=total)


def job_rescore_batch() -> None:
    """관심종목 정기 스코어 재계산 (trigger_type='batch', Phase 4)."""
    from ..core import db
    from ..pipeline import scoring

    rows = db.fetch_all("SELECT DISTINCT corp_code FROM user_watchlist")
    ok, failed = 0, 0
    for row in rows:
        try:
            scoring.rescore_live(row["corp_code"], trigger_type="batch")
            ok += 1
        except Exception:
            log.exception("정기 재스코어링 실패", corp_code=row["corp_code"])
            failed += 1
    log.info("정기 재스코어링 배치 완료", ok=ok, failed=failed)


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 주 1회 일요일 03:00 — 기업코드 마스터
    scheduler.add_job(
        job_sync_corp_codes, CronTrigger(day_of_week="sun", hour=3), id="sync_corp_codes"
    )
    # 매일 06:00 — 재무제표 / 컨센서스
    scheduler.add_job(job_sync_financials, CronTrigger(hour=6), id="sync_financials")
    scheduler.add_job(job_sync_consensus, CronTrigger(hour=6, minute=30), id="sync_consensus")
    # 매월 1일 04:00 — 거시지표
    scheduler.add_job(job_sync_macro, CronTrigger(day=1, hour=4), id="sync_macro")
    # N분 주기 — 뉴스 폴링
    scheduler.add_job(
        job_poll_news,
        IntervalTrigger(minutes=settings.news_poll_interval_minutes),
        id="poll_news",
    )
    # 매일 07:00 — 정기 재스코어링
    scheduler.add_job(job_rescore_batch, CronTrigger(hour=7), id="rescore_batch")

    return scheduler


if __name__ == "__main__":
    log.info("스케줄러 기동", news_interval_min=settings.news_poll_interval_minutes)
    build_scheduler().start()
