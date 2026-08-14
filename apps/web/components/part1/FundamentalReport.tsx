"use client";

import { useScorePolling } from "@/lib/hooks/useScorePolling";
import ModeBadge from "@/components/shared/ModeBadge";

/**
 * Part 1: 스코어 게이지 + 4개 팩터 바(가중치 표시) + 근거 카드 + 컨센서스 패널.
 * 컨센서스는 final_score 에 포함되지 않는 참고 정보로 분리 표기한다 (§7).
 */
export default function FundamentalReport({ stockCode }: { stockCode: string }) {
  const { score, error, isLoading } = useScorePolling(stockCode, "demo-user");

  if (isLoading) return <section className="text-neutral-500">불러오는 중…</section>;
  if (error) return <section className="text-red-400">스코어를 불러오지 못했습니다.</section>;
  if (!score) return null;

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

      {/* TODO(Phase 7): 팩터 바(Recharts), 근거 카드, 컨센서스 패널 */}

      <p className="mt-6 text-xs text-neutral-500">
        본 스코어는 참고용 정보이며, 투자 권유가 아닙니다.
      </p>
    </section>
  );
}
