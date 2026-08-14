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
    raise NotImplementedError("Phase 1")


def job_poll_news() -> None:
    """관심종목 뉴스 폴링 (NEWS_POLL_INTERVAL_MINUTES 주기, Phase 2)."""
    raise NotImplementedError("Phase 2")


def job_sync_macro() -> None:
    """ECOS 거시지표 월 배치 (Phase 3)."""
    from ..ingestion import ecos_client

    count = ecos_client.sync_all_indicators()
    log.info("거시지표 동기화 완료", count=count)


def job_sync_consensus() -> None:
    """애널리스트 컨센서스 일 배치 (Phase 3)."""
    raise NotImplementedError("Phase 3")


def job_rescore_batch() -> None:
    """관심종목 정기 스코어 재계산 (trigger_type='batch', Phase 4)."""
    raise NotImplementedError("Phase 4")


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
