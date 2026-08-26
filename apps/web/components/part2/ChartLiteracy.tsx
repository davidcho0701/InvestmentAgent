"use client";

import useSWR from "swr";
import CandleChart from "@/components/part2/CandleChart";
import { fetcher } from "@/lib/api";
import { useRealtimeCandles } from "@/lib/hooks/useRealtimeCandles";
import type { Candle, ChartAnnotation, ChartResponse } from "@/lib/types";

const USER_ID = "demo-user";
const numberFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

export default function ChartLiteracy({ stockCode }: { stockCode: string }) {
  const { data: chart, error, isLoading } = useSWR<ChartResponse>(
    `/api/chart/${stockCode}?user_id=${USER_ID}`,
    fetcher,
  );
  const live = useRealtimeCandles(stockCode, chart?.mode === "realtime");
  const candles = mergeCandles(chart?.candles ?? [], live.candles);
  const annotations = mergeAnnotations(chart?.annotations ?? [], live.annotations);
  const latest = candles.at(-1);

  if (isLoading) return <section className="text-neutral-500">차트를 불러오는 중입니다.</section>;
  if (error) return <section className="text-red-400">차트 데이터를 불러오지 못했습니다.</section>;

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-5 shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">차트 쉽게 읽기</h2>
          <p className="mt-1 text-xs text-neutral-500">수치와 봉 모양을 쉬운 말로 풀이합니다.</p>
        </div>
        {chart?.mode === "realtime" ? (
          <span className="rounded-full bg-red-500/10 px-2.5 py-1 text-xs text-red-300">
            실시간 · {live.connected ? "연결됨" : "연결 대기"}
          </span>
        ) : (
          <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300">
            스냅샷
          </span>
        )}
      </header>

      {latest ? (
        <>
          <CandleChart candles={candles} annotations={annotations} />
          <div className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
            <Metric label="시가" value={latest.open} />
            <Metric label="고가" value={latest.high} />
            <Metric label="저가" value={latest.low} />
            <Metric label="종가" value={latest.close} />
            <Metric label="거래량" value={latest.volume} />
          </div>
        </>
      ) : (
        <div className="mt-4 rounded-lg bg-neutral-900 p-4 text-sm text-neutral-400">
          아직 표시할 캔들이 없습니다. 관심종목을 등록한 뒤 실시간 체결이 들어오면 차트가 채워집니다.
        </div>
      )}

      <section className="mt-5" aria-label="차트 해설">
        <h3 className="text-sm font-medium text-neutral-200">패턴 해설</h3>
        {annotations.length ? (
          <div className="mt-2 space-y-2">
            {annotations.slice(-3).reverse().map((annotation) => (
              <article
                key={`${annotation.ts}-${annotation.pattern_label}`}
                className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-3"
              >
                <p className="text-sm font-medium text-amber-200">{annotation.pattern_label}</p>
                <p className="mt-1 text-sm leading-6 text-neutral-300">{annotation.explanation_text}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">
            패턴이 감지되면 이곳에 수치와 함께 쉬운 설명이 표시됩니다.
          </p>
        )}
      </section>

      <details className="mt-5 rounded-lg border border-neutral-800 p-3 text-sm text-neutral-300">
        <summary className="cursor-pointer font-medium text-neutral-100">용어 사전</summary>
        <dl className="mt-3 grid gap-3 leading-6">
          <GlossaryTerm
            term="봉(캔들)"
            description="일정 시간 동안의 시가·고가·저가·종가를 한 개의 막대로 나타낸 것입니다. 이 화면에서는 1분을 한 봉으로 묶습니다."
          />
          <GlossaryTerm
            term="거래량"
            description="그 시간에 실제로 체결된 수량입니다. 가격의 방향을 뜻하지 않고, 체결이 얼마나 활발했는지 보여주는 수치입니다."
          />
          <GlossaryTerm
            term="이동평균선"
            description="여러 봉의 종가 평균을 이은 선입니다. 짧은 기간선과 긴 기간선의 위치를 비교해 최근 가격 흐름을 살펴볼 수 있습니다."
          />
          <GlossaryTerm
            term="RSI(14)"
            description="최근 14개 구간의 가격 변화 강도를 0~100으로 표현한 보조지표입니다. 높고 낮음은 상태를 보여주는 수치일 뿐 행동 지시가 아닙니다."
          />
        </dl>
      </details>

      <p className="mt-4 text-xs leading-5 text-neutral-500">
        차트 해설은 학습과 정보 제공 목적입니다. 매수·매도 판단을 제시하지 않으며, 향후 가격 방향을 보장하는 투자 신호가 아닙니다.
      </p>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-neutral-900 px-3 py-2">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="mt-0.5 font-medium text-neutral-100">{numberFormatter.format(value)}</p>
    </div>
  );
}

function GlossaryTerm({ term, description }: { term: string; description: string }) {
  return (
    <div>
      <dt className="font-medium text-neutral-100">{term}</dt>
      <dd className="text-neutral-400">{description}</dd>
    </div>
  );
}

function mergeCandles(initial: Candle[], streamed: Candle[]): Candle[] {
  const byTime = new Map(initial.map((candle) => [candle.time, candle]));
  for (const candle of streamed) byTime.set(candle.time, candle);
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

function mergeAnnotations(initial: ChartAnnotation[], streamed: ChartAnnotation[]): ChartAnnotation[] {
  const byKey = new Map(
    initial.map((annotation) => [`${annotation.ts}-${annotation.pattern_label}`, annotation]),
  );
  for (const annotation of streamed) {
    byKey.set(`${annotation.ts}-${annotation.pattern_label}`, annotation);
  }
  return [...byKey.values()].sort((a, b) => a.ts - b.ts);
}
