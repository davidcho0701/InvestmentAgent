"""캔들 패턴 + 기술지표 감지 및 해설 생성 (Part 2 §4.1, Phase 5).

제약(§7): 생성되는 모든 문장은 중립 어미로 끝나고 "매매 신호가 아님" 문구를 동반한다.
매수/매도 권유 표현은 어떤 경로로도 생성하지 않는다.
"""
from __future__ import annotations

from typing import Any

from ..core import get_logger

log = get_logger(__name__)

DISCLAIMER = "본 해설은 차트 형태에 대한 설명이며, 매매 신호가 아닙니다."

# 규칙 기반 라벨 -> 중립 서술 템플릿
PATTERN_TEMPLATES: dict[str, str] = {
    "long_upper_shadow": "고가 대비 종가가 크게 밀리며 위꼬리가 길게 남은 형태입니다. 장중 상승분이 유지되지 못한 구간으로 해석됩니다.",
    "long_lower_shadow": "저가 대비 종가가 회복되며 아래꼬리가 길게 남은 형태입니다. 장중 하락분이 되돌려진 구간으로 해석됩니다.",
    "doji": "시가와 종가가 거의 같은 도지 형태로, 매수·매도 힘이 균형을 이룬 구간입니다.",
    "marubozu_bull": "꼬리가 거의 없는 양봉으로, 시가부터 종가까지 한 방향 흐름이 이어진 구간입니다.",
    "marubozu_bear": "꼬리가 거의 없는 음봉으로, 시가부터 종가까지 한 방향 흐름이 이어진 구간입니다.",
    "gap_up": "직전 봉의 고가보다 높게 시작해 가격 공백(갭)이 생긴 구간입니다.",
    "gap_down": "직전 봉의 저가보다 낮게 시작해 가격 공백(갭)이 생긴 구간입니다.",
    "volume_surge": "평소 대비 거래량이 크게 늘어난 구간입니다.",
    "golden_cross": "단기 이동평균선이 장기선을 위로 통과한 구간입니다.",
    "dead_cross": "단기 이동평균선이 장기선을 아래로 통과한 구간입니다.",
    "rsi_overbought": "RSI가 과매수 기준선 위에 위치한 구간입니다.",
    "rsi_oversold": "RSI가 과매도 기준선 아래에 위치한 구간입니다.",
}


def detect_candle_patterns(df: Any) -> list[dict[str, Any]]:
    """OHLCV DataFrame -> [{ts, pattern_label}] (pandas-ta + 규칙 기반)."""
    raise NotImplementedError("Phase 5")


def compute_indicators(df: Any) -> Any:
    """이동평균(5/20/60), RSI, 거래량 급증 플래그를 컬럼으로 추가한 DataFrame 반환."""
    raise NotImplementedError("Phase 5")


def build_explanation(pattern_label: str, indicator_flags: dict[str, Any]) -> str:
    """템플릿 기반 중립 해설 문장 + 면책 문구."""
    base = PATTERN_TEMPLATES.get(pattern_label)
    if base is None:
        return DISCLAIMER
    return f"{base} {DISCLAIMER}"


def annotate(stock_code: str, df: Any) -> list[dict[str, Any]]:
    """패턴 감지 -> 해설 생성 -> fact_chart_annotation 적재용 목록 반환."""
    raise NotImplementedError("Phase 5")
