"use client";

/**
 * Part 2: TradingView Lightweight Charts + 패턴 마커 클릭 시 해설 카드.
 * 제약(§7): 어떤 경우에도 매수/매도 권유 문장을 표시하지 않는다.
 */
export default function ChartLiteracy({ stockCode }: { stockCode: string }) {
  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold">차트 해설</h2>

      {/* TODO(Phase 7): lightweight-charts 연동, useRealtimeCandles, 패턴 마커/해설 카드 */}
      <div className="mt-4 flex h-64 items-center justify-center rounded-md bg-neutral-900 text-sm text-neutral-600">
        차트 영역 ({stockCode})
      </div>

      <p className="mt-4 text-xs text-neutral-500">
        본 해설은 차트 형태에 대한 설명이며, 매매 신호가 아닙니다.
      </p>
    </section>
  );
}
