from __future__ import annotations

import unittest

from apps.worker.pipeline.pattern_detection import annotate, build_explanation, compute_indicators


class PatternDetectionTests(unittest.TestCase):
    def test_long_candle_and_volume_explanations_are_beginner_safe(self) -> None:
        rows = [
            {
                "ts": minute,
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.1,
                "volume": 10,
            }
            for minute in range(20)
        ]
        rows.append(
            {
                "ts": 20,
                "open": 100,
                "high": 115,
                "low": 99,
                "close": 114,
                "volume": 30,
            }
        )

        annotations = annotate("005930", rows)
        by_label = {annotation["pattern_label"]: annotation for annotation in annotations}

        self.assertIn("장대양봉", by_label)
        self.assertIn("거래량 급증", by_label)
        self.assertEqual(by_label["거래량 급증"]["indicator_flags"]["volume_ratio"], 3.0)
        self.assertIn("최근 20개 봉 평균의 약 3.0배", by_label["거래량 급증"]["explanation_text"])
        for annotation in annotations:
            self.assertIn("투자 신호가 아닙니다", annotation["explanation_text"])

    def test_indicators_wait_for_the_required_history(self) -> None:
        rows = [
            {
                "ts": minute,
                "open": 100 + minute,
                "high": 101 + minute,
                "low": 99 + minute,
                "close": 100 + minute,
                "volume": 10,
            }
            for minute in range(15)
        ]

        indicators = compute_indicators(rows)

        self.assertEqual(indicators[3]["ma5"], None)
        self.assertEqual(indicators[4]["ma5"], 102.0)
        self.assertEqual(indicators[14]["rsi14"], 100.0)
        self.assertEqual(indicators[14]["volume_ratio"], None)

    def test_unknown_label_still_has_disclaimer(self) -> None:
        explanation = build_explanation("unknown", {})
        self.assertIn("투자 신호가 아닙니다", explanation)


if __name__ == "__main__":
    unittest.main()
