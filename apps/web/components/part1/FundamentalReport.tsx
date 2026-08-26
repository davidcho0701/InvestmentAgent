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

const FACTOR_COLOR = "#f97316";

/**
 * Part 1: 스코어 게이지 + 4개 팩터 바(가중치 표시) + 근거 카드 + 컨센서스 패널.
 * 컨센서스는 final_score 에 포함되지 않는 참고 정보로 분리 표기한다 (§7).
 */
export default function FundamentalReport({ stockCode }: { stockCode: string }) {
  const { score, error, isLoading } = useScorePolling(stockCode, "demo-user");

  if (isLoading) return <section className="text-neutral-500">불러오는 중…</section>;
  if (error) return <section className="text-red-400">스코어를 불러오지 못했습니다.</section>;
  if (!score) return null;

  const factorEntries = Object.entries(score.contributing_factors) as [string, FactorDetail][];
  const factorData = factorEntries.map(([key, detail]) => ({
    key,
    label: FACTOR_LABELS[key] ?? key,
    score: detail.score,
    weight: detail.weight,
  }));

  const consensus = score.analyst_consensus;

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <header className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{score.corp_name}</h2>
        <ModeBadge mode={score.mode} asOf={score.as_of} />
      </header>

      <div className="mt-6">
        <div className="text-4xl font-bold">{score.final_score}</div>
        <div className="mt-1 text-sm text-neutral-400">{score.recommendation_label}</div>
      </div>

      <div className="mt-6 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={factorData} layout="vertical" margin={{ left: 8, right: 16 }}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis
              type="category"
              dataKey="label"
              width={84}
              tick={{ fill: "#a3a3a3", fontSize: 12 }}
              axisLine={false}
              tickLine={false}
            />
            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={16}>
              {factorData.map((d) => (
                <Cell key={d.key} fill={FACTOR_COLOR} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
        {factorData.map((d) => (
          <li key={d.key}>
            {d.label} 가중치 {Math.round(d.weight * 100)}%
          </li>
        ))}
      </ul>

      {score.evidence?.length > 0 && (
        <div className="mt-6 rounded-md border border-neutral-800 bg-neutral-900/50 p-3">
          <h3 className="text-sm font-medium text-neutral-300">근거</h3>
          <ul className="mt-2 space-y-1 text-sm text-neutral-400">
            {score.evidence.map((sentence) => (
              <li key={sentence}>· {sentence}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 rounded-md border border-neutral-800 p-3">
        <h3 className="text-sm font-medium text-neutral-300">
          애널리스트 컨센서스{" "}
          <span className="font-normal text-neutral-600">(참고용 · 스코어에 미반영)</span>
        </h3>
        {consensus && consensus.report_count > 0 ? (
          <div className="mt-2 text-sm text-neutral-400">
            <div>
              평균 목표주가:{" "}
              {consensus.avg_target_price
                ? `${Math.round(consensus.avg_target_price).toLocaleString()}원`
                : "데이터 없음"}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(consensus.opinion_counts).map(([opinion, count]) => (
                <span key={opinion}>
                  {opinion} {count}건
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-neutral-500">최근 90일 내 컨센서스 데이터 없음</p>
        )}
      </div>

      <p className="mt-6 text-xs text-neutral-500">
        본 스코어는 참고용 정보이며, 투자 권유가 아닙니다.
      </p>
    </section>
  );
}
