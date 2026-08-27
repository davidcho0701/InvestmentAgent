"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { useScorePolling } from "@/lib/hooks/useScorePolling";
import ModeBadge from "@/components/shared/ModeBadge";
import type { FactorDetail } from "@/lib/types";

const FACTOR_LABELS: Record<string, string> = {
  financial_health: "재무 건전성",
  financial_growth: "성장성",
  news_sentiment: "뉴스 감성",
  macro_adjustment: "거시 환경",
};

type Band = "high" | "mid" | "low";
const BAND_HEX: Record<Band, string> = { high: "#2dd4bf", mid: "#f59e0b", low: "#f43f5e" };
const BAND_TEXT: Record<Band, string> = {
  high: "text-score-high",
  mid: "text-score-mid",
  low: "text-score-low",
};

function bandOf(score: number): Band {
  if (score >= 55) return "high";
  if (score >= 45) return "mid";
  return "low";
}

/**
 * Part 1: 스코어 게이지 + 4개 팩터 바(가중치 표시) + 근거 카드 + 컨센서스 패널.
 * 컨센서스는 final_score 에 포함되지 않는 참고 정보로 분리 표기한다 (§7).
 */
export default function FundamentalReport({ stockCode }: { stockCode: string }) {
  const { score, error, isLoading } = useScorePolling(stockCode, "demo-user");

  if (isLoading) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-panel">
        <p className="text-sm text-neutral-500">불러오는 중…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-panel">
        <p className="text-sm text-rose-400">스코어를 불러오지 못했습니다.</p>
      </section>
    );
  }
  if (!score) return null;

  const factorEntries = Object.entries(score.contributing_factors) as [string, FactorDetail][];
  const factorData = factorEntries.map(([key, detail]) => ({
    key,
    label: FACTOR_LABELS[key] ?? key,
    score: detail.score,
    weight: detail.weight,
  }));

  const consensus = score.analyst_consensus;
  const band = bandOf(score.final_score);

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-panel">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-neutral-50">{score.corp_name}</h2>
          <p className="mt-0.5 font-mono text-xs tabular-nums text-neutral-600">{score.stock_code}</p>
        </div>
        <ModeBadge mode={score.mode} asOf={score.as_of} />
      </header>

      <div className="mt-6 flex items-end justify-between">
        <div>
          <div className={`font-mono text-5xl font-bold tabular-nums ${BAND_TEXT[band]}`}>
            {score.final_score.toFixed(1)}
            <span className="ml-1 text-lg font-medium text-neutral-600">/100</span>
          </div>
          <div className="mt-1.5 text-sm font-medium text-neutral-300">
            {score.recommendation_label}
          </div>
        </div>
      </div>

      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-raised">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.max(0, Math.min(100, score.final_score))}%`,
            backgroundColor: BAND_HEX[band],
          }}
        />
      </div>

      <div className="mt-7 h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={factorData} layout="vertical" margin={{ left: 0, right: 20 }} barGap={6}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              type="category"
              dataKey="label"
              width={88}
              tick={{ fill: "#8a94a3", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={14} background={{ fill: "#171c25" }}>
              {factorData.map((d) => (
                <Cell key={d.key} fill={BAND_HEX[bandOf(d.score)]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-neutral-600">
        {factorData.map((d) => (
          <li key={d.key} className="font-mono tabular-nums">
            {d.label} · {Math.round(d.weight * 100)}%
          </li>
        ))}
      </ul>

      {score.evidence?.length > 0 && (
        <div className="mt-6 rounded-lg border border-surface-border bg-surface-raised/60 p-3.5">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">근거</h3>
          <ul className="mt-2.5 space-y-1.5">
            {score.evidence.map((sentence) => (
              <li key={sentence} className="flex items-start gap-2 text-sm leading-5 text-neutral-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-neutral-600" />
                {sentence}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3 rounded-lg border border-surface-border p-3.5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
          애널리스트 컨센서스{" "}
          <span className="font-normal normal-case tracking-normal text-neutral-700">
            · 참고용, 스코어 미반영
          </span>
        </h3>
        {consensus && consensus.report_count > 0 ? (
          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-mono text-xl font-semibold tabular-nums text-neutral-100">
                {consensus.avg_target_price
                  ? `${Math.round(consensus.avg_target_price).toLocaleString()}원`
                  : "데이터 없음"}
              </p>
              <p className="text-[11px] text-neutral-600">평균 목표주가 · 최근 90일 {consensus.report_count}건</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(consensus.opinion_counts).map(([opinion, count]) => (
                <span
                  key={opinion}
                  className="rounded-full border border-surface-border bg-surface-raised px-2.5 py-1 text-xs text-neutral-300"
                >
                  {opinion} <span className="font-mono tabular-nums text-neutral-500">{count}</span>
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-neutral-600">최근 90일 내 컨센서스 데이터 없음</p>
        )}
      </div>

      <p className="mt-5 text-[11px] leading-5 text-neutral-700">
        본 스코어는 참고용 정보이며, 투자 권유가 아닙니다.
      </p>
    </section>
  );
}
