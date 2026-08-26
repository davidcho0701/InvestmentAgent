"""Explain chart patterns using transparent, rule-based calculations.

This module deliberately does not predict prices or recommend trades. It turns
OHLCV values into beginner-friendly observations and attaches the same
non-signal disclaimer to every explanation.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import fmean
from typing import Any

DISCLAIMER = "이 설명은 차트 형태와 수치를 이해하기 위한 정보이며, 향후 가격 방향을 보장하는 투자 신호가 아닙니다."

PATTERN_LABELS: dict[str, str] = {
    "doji": "도지",
    "long_bullish": "장대양봉",
    "long_bearish": "장대음봉",
    "long_upper_shadow": "윗꼬리 긴 봉",
    "long_lower_shadow": "아랫꼬리 긴 봉",
    "gap_up": "상승 갭",
    "gap_down": "하락 갭",
    "volume_surge": "거래량 급증",
    "golden_cross": "골든크로스",
    "dead_cross": "데드크로스",
    "rsi_overbought": "RSI 과열 구간",
    "rsi_oversold": "RSI 침체 구간",
}

PATTERN_TEMPLATES: dict[str, str] = {
    "doji": "시가와 종가가 거의 같은 봉입니다. 이 구간에서는 매수와 매도 힘이 팽팽했던 모습으로 해석할 수 있습니다.",
    "long_bullish": "몸통이 최근 봉보다 긴 양봉입니다. 해당 분에는 가격이 시가보다 높은 곳에서 마감된 모습입니다.",
    "long_bearish": "몸통이 최근 봉보다 긴 음봉입니다. 해당 분에는 가격이 시가보다 낮은 곳에서 마감된 모습입니다.",
    "long_upper_shadow": "윗꼬리가 긴 봉입니다. 높은 가격대까지 움직인 뒤 종가가 그보다 낮은 곳에 형성된 모습입니다.",
    "long_lower_shadow": "아랫꼬리가 긴 봉입니다. 낮은 가격대까지 움직인 뒤 종가가 그보다 높은 곳에 형성된 모습입니다.",
    "gap_up": "직전 봉의 고가보다 높은 가격에서 시작한 가격 공백 구간입니다.",
    "gap_down": "직전 봉의 저가보다 낮은 가격에서 시작한 가격 공백 구간입니다.",
    "volume_surge": "최근 평균보다 거래량이 크게 늘어난 구간입니다. 평소보다 체결이 활발했는지 살펴볼 수 있습니다.",
    "golden_cross": "짧은 기간의 평균 가격선이 긴 기간의 평균 가격선을 위로 통과한 상태입니다.",
    "dead_cross": "짧은 기간의 평균 가격선이 긴 기간의 평균 가격선을 아래로 통과한 상태입니다.",
    "rsi_overbought": "최근 가격 변화의 강도를 나타내는 RSI가 높은 구간입니다.",
    "rsi_oversold": "최근 가격 변화의 강도를 나타내는 RSI가 낮은 구간입니다.",
}

_LABEL_TO_KEY = {label: key for key, label in PATTERN_LABELS.items()}


def compute_indicators(data: Any) -> list[dict[str, Any]]:
    """Add transparent MA, RSI(14), and volume-ratio values to OHLCV rows.

    ``data`` may be a sequence of mapping objects or a pandas DataFrame. A
    list of plain dictionaries is returned so the streaming worker does not
    require pandas at import time.
    """

    rows = _normalise_rows(data)
    closes: list[float] = []
    volumes: list[float] = []
    enriched: list[dict[str, Any]] = []

    for row in rows:
        close = row["close"]
        previous_volumes = volumes[-20:]
        closes.append(close)
        volumes.append(row["volume"])
        enriched.append(
            {
                **row,
                "ma5": _moving_average(closes, 5),
                "ma20": _moving_average(closes, 20),
                "ma60": _moving_average(closes, 60),
                "rsi14": _rsi14(closes),
                "volume_ratio": (
                    row["volume"] / fmean(previous_volumes)
                    if len(previous_volumes) == 20 and fmean(previous_volumes) > 0
                    else None
                ),
            }
        )
    return enriched


def detect_candle_patterns(data: Any) -> list[dict[str, Any]]:
    """Return detected rule-based patterns for every supplied OHLCV row."""

    rows = compute_indicators(data)
    detections: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        body = abs(row["close"] - row["open"])
        candle_range = row["high"] - row["low"]
        prior_bodies = [
            abs(previous["close"] - previous["open"])
            for previous in rows[max(0, index - 20) : index]
        ]
        average_prior_body = fmean(prior_bodies) if prior_bodies else None

        keys: list[str] = []
        if candle_range > 0 and body / candle_range <= 0.1:
            keys.append("doji")
        if (
            average_prior_body is not None
            and len(prior_bodies) >= 5
            and body >= average_prior_body * 1.8
            and candle_range > 0
            and body / candle_range >= 0.6
        ):
            keys.append("long_bullish" if row["close"] > row["open"] else "long_bearish")

        upper_shadow = row["high"] - max(row["open"], row["close"])
        lower_shadow = min(row["open"], row["close"]) - row["low"]
        if candle_range > 0 and upper_shadow / candle_range >= 0.55 and upper_shadow > body:
            keys.append("long_upper_shadow")
        if candle_range > 0 and lower_shadow / candle_range >= 0.55 and lower_shadow > body:
            keys.append("long_lower_shadow")

        if index > 0:
            previous = rows[index - 1]
            if row["open"] > previous["high"]:
                keys.append("gap_up")
            elif row["open"] < previous["low"]:
                keys.append("gap_down")
            if _crossed_above(previous, row):
                keys.append("golden_cross")
            elif _crossed_below(previous, row):
                keys.append("dead_cross")

        if row["volume_ratio"] is not None and row["volume_ratio"] >= 2.0:
            keys.append("volume_surge")
        if row["rsi14"] is not None:
            if row["rsi14"] >= 70:
                keys.append("rsi_overbought")
            elif row["rsi14"] <= 30:
                keys.append("rsi_oversold")

        indicator_flags = _indicator_flags(row)
        for key in keys:
            detections.append(
                {
                    "ts": row["ts"],
                    "pattern_key": key,
                    "pattern_label": PATTERN_LABELS[key],
                    "indicator_flags": indicator_flags,
                }
            )
    return detections


def build_explanation(pattern_label: str, indicator_flags: Mapping[str, Any]) -> str:
    """Build a neutral, beginner-friendly explanation and mandatory disclaimer."""

    key = pattern_label if pattern_label in PATTERN_TEMPLATES else _LABEL_TO_KEY.get(pattern_label)
    base = PATTERN_TEMPLATES.get(key or "", "관찰된 차트 상태를 이해하기 위한 참고 정보입니다.")
    details: list[str] = []
    volume_ratio = _number(indicator_flags.get("volume_ratio"))
    rsi14 = _number(indicator_flags.get("rsi14"))
    if key == "volume_surge" and volume_ratio is not None:
        details.append(f"현재 거래량은 최근 20개 봉 평균의 약 {volume_ratio:.1f}배입니다.")
    if key in {"rsi_overbought", "rsi_oversold"} and rsi14 is not None:
        details.append(f"현재 RSI(14)는 {rsi14:.1f}입니다.")
    return " ".join([base, *details, DISCLAIMER])


def annotate(stock_code: str, data: Any) -> list[dict[str, Any]]:
    """Return API/DB-ready annotations for detected patterns without side effects."""

    code = str(stock_code).strip()
    if not code:
        raise ValueError("stock_code is required")
    annotations: list[dict[str, Any]] = []
    for detected in detect_candle_patterns(data):
        annotations.append(
            {
                "stock_code": code,
                "ts": detected["ts"],
                "pattern_label": detected["pattern_label"],
                "indicator_flags": detected["indicator_flags"],
                "explanation_text": build_explanation(
                    detected["pattern_key"], detected["indicator_flags"]
                ),
            }
        )
    return annotations


def _normalise_rows(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_dict"):
        records = data.to_dict("records")
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        records = data
    else:
        raise TypeError("OHLCV data must be a sequence of mappings or a DataFrame")

    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise TypeError(f"OHLCV row {index} must be a mapping")
        timestamp = record.get("ts", record.get("timestamp", record.get("time", index)))
        row = {
            "ts": timestamp,
            "open": _required_number(record, "open"),
            "high": _required_number(record, "high"),
            "low": _required_number(record, "low"),
            "close": _required_number(record, "close"),
            "volume": _required_number(record, "volume"),
        }
        if row["high"] < max(row["open"], row["close"], row["low"]) or row["low"] > min(
            row["open"], row["close"], row["high"]
        ):
            raise ValueError(f"Invalid OHLCV row {index}: high/low range is inconsistent")
        if row["volume"] < 0:
            raise ValueError(f"Invalid OHLCV row {index}: volume cannot be negative")
        rows.append(row)
    return rows


def _required_number(record: Mapping[str, Any], key: str) -> float:
    if key not in record:
        raise ValueError(f"missing {key}")
    value = _number(record[key])
    if value is None:
        raise ValueError(f"{key} must be numeric")
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and numeric not in {float("inf"), float("-inf")} else None


def _moving_average(values: list[float], period: int) -> float | None:
    return fmean(values[-period:]) if len(values) >= period else None


def _rsi14(closes: list[float]) -> float | None:
    if len(closes) < 15:
        return None
    changes = [later - earlier for earlier, later in zip(closes[-15:-1], closes[-14:])]
    average_gain = fmean(max(change, 0.0) for change in changes)
    average_loss = fmean(max(-change, 0.0) for change in changes)
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def _crossed_above(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    return all(
        value is not None
        for value in (previous["ma5"], previous["ma20"], current["ma5"], current["ma20"])
    ) and previous["ma5"] <= previous["ma20"] < current["ma5"]


def _crossed_below(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    return all(
        value is not None
        for value in (previous["ma5"], previous["ma20"], current["ma5"], current["ma20"])
    ) and previous["ma5"] >= previous["ma20"] > current["ma5"]


def _indicator_flags(row: Mapping[str, Any]) -> dict[str, float]:
    return {
        key: round(value, 4)
        for key in ("ma5", "ma20", "ma60", "rsi14", "volume_ratio")
        if (value := row.get(key)) is not None
    }
