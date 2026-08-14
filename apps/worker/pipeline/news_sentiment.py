"""뉴스 감성분석 (§3.2.3, Phase 2).

로컬 CPU 추론(KR-FinBERT)이 기본. 고영향 기사에 한해서만 LLM 으로 근거 문장을 생성한다.
모델은 서버 기동 시 1회만 로드한다.
"""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)

MODEL_NAME = "snunlp/KR-FinBert-SC"

_pipeline = None


def get_sentiment_pipeline():
    """transformers pipeline 지연 로딩 (프로세스당 1회)."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline as hf_pipeline

        log.info("감성분석 모델 로딩", model=MODEL_NAME)
        _pipeline = hf_pipeline("sentiment-analysis", model=MODEL_NAME, device=-1)
    return _pipeline


def analyze_sentiment(text: str) -> float:
    """-1(부정) ~ +1(긍정) 연속값으로 변환."""
    raise NotImplementedError("Phase 2")


def is_high_impact(sentiment_score: float) -> bool:
    """config.yaml news.high_impact_threshold 기준 고영향 판정."""
    from ..core.config import get_scoring_config

    threshold = get_scoring_config()["news"]["high_impact_threshold"]
    return abs(sentiment_score) > threshold


def generate_evidence_with_llm(title: str, body: str) -> str:
    """고영향 기사에 한해 LLM 으로 근거 문장 1~2줄 생성. 호출 최소화."""
    raise NotImplementedError("Phase 2")


def update_rolling_sentiment(corp_code: str) -> float:
    """최근 30일 기사에 시간가중 반감기를 적용한 롤링 점수 계산 + Redis 갱신."""
    raise NotImplementedError("Phase 2")


def process_news_batch(corp_code: str) -> dict[str, Any]:
    """검색 -> 중복제거 -> 감성분석 -> 저장 -> 롤링 갱신 까지의 단일 진입점."""
    raise NotImplementedError("Phase 2")
