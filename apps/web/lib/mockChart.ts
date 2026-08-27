import type { Candle, ChartAnnotation } from "./types";

/**
 * 장 마감 등으로 실데이터(캔들)가 하나도 없을 때만 쓰는 데모용 목업 생성기.
 * 종목코드로 시드를 고정해 같은 종목은 항상 같은 모양이 나오게 한다.
 * 실데이터가 있으면 절대 쓰이지 않는다 (ChartLiteracy.tsx 의 폴백 분기 참고).
 */

function seedFromString(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function buildMockChart(seedKey: string, count = 90): {
  candles: Candle[];
  annotations: ChartAnnotation[];
} {
  const rand = mulberry32(seedFromString(seedKey));
  const basePrice = 20000 + Math.floor(rand() * 130) * 1000; // 2만~15만원대, 1천원 단위

  const nowMinute = Math.floor(Date.now() / 60000) * 60;
  const startTime = nowMinute - (count - 1) * 60;
  const bigUpIndex = Math.floor(count * 0.32);
  const dojiIndex = Math.floor(count * 0.58);
  const volumeSpikeIndex = Math.floor(count * 0.8);

  const candles: Candle[] = [];
  let prevClose = basePrice;

  for (let i = 0; i < count; i++) {
    const open = prevClose;
    let driftPct = (rand() - 0.5) * 0.006; // 기본 변동폭 ±0.3%

    if (i === bigUpIndex) driftPct = 0.021 + rand() * 0.01; // 장대양봉
    if (i === dojiIndex) driftPct = (rand() - 0.5) * 0.0006; // 도지(시가≈종가)

    const close = Math.max(1, open * (1 + driftPct));
    const wick = Math.abs(driftPct) * (0.3 + rand() * 0.6) + open * 0.0008;
    const high = Math.max(open, close) + wick * rand();
    const low = Math.min(open, close) - wick * rand();

    const baseVolume = 8000 + rand() * 25000;
    const volume = i === volumeSpikeIndex ? baseVolume * (3 + rand()) : baseVolume;

    candles.push({
      time: startTime + i * 60,
      open: round(open),
      high: round(high),
      low: round(low),
      close: round(close),
      volume: Math.round(volume),
    });
    prevClose = close;
  }

  const annotations: ChartAnnotation[] = [
    {
      ts: candles[bigUpIndex].time,
      pattern_label: "장대양봉",
      indicator_flags: {},
      explanation_text:
        "시가 대비 종가가 크게 오르며 몸통이 길게 형성된 구간입니다. 매수 심리가 강했던 구간으로 해석되며, 이후 방향을 보장하지는 않습니다.",
    },
    {
      ts: candles[dojiIndex].time,
      pattern_label: "도지",
      indicator_flags: {},
      explanation_text: "시가와 종가가 거의 같은 도지 형태로, 매수·매도 힘이 균형을 이룬 구간입니다.",
    },
    {
      ts: candles[volumeSpikeIndex].time,
      pattern_label: "거래량 급증",
      indicator_flags: {},
      explanation_text:
        "직전 구간 평균 대비 거래량이 크게 늘어난 구간입니다. 체결이 활발했음을 보여줄 뿐, 가격 방향을 의미하지는 않습니다.",
    },
  ];

  return { candles, annotations };
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}
