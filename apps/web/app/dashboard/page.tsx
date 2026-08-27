"use client";

import { useState } from "react";
import Link from "next/link";
import CompanySelector from "@/components/shared/CompanySelector";
import LogoMark from "@/components/shared/LogoMark";
import FundamentalReport from "@/components/part1/FundamentalReport";
import LlmNewsEvidence from "@/components/part1/LlmNewsEvidence";
import ChartLiteracy from "@/components/part2/ChartLiteracy";

export default function DashboardPage() {
  const [stockCode, setStockCode] = useState<string | null>(null);

  return (
    <div className="flex h-screen flex-col bg-surface-base">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-surface-border px-4">
        <div className="flex items-center gap-2">
          <Link
            href="/"
            aria-label="홈으로 돌아가기"
            className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 transition hover:bg-surface-raised hover:text-neutral-200"
          >
            ←
          </Link>
          <span className="flex h-5 w-5 items-center justify-center rounded bg-accent/15 text-accent">
            <LogoMark className="h-3.5 w-3.5" />
          </span>
          <span className="text-sm font-semibold tracking-wide text-neutral-100">
            NewsFin Quant
          </span>
          <span className="ml-2 hidden text-xs text-neutral-600 sm:inline">
            설명 가능한 투자 스코어
          </span>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 border-r border-surface-border bg-surface md:flex md:flex-col">
          <CompanySelector onSelect={setStockCode} selected={stockCode} />
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="border-b border-surface-border p-4 md:hidden">
            <CompanySelector onSelect={setStockCode} selected={stockCode} />
          </div>

          {stockCode ? (
            <div className="grid gap-4 p-4 lg:grid-cols-2">
              <div className="space-y-4">
                <FundamentalReport stockCode={stockCode} />
                <LlmNewsEvidence stockCode={stockCode} />
              </div>
              <ChartLiteracy stockCode={stockCode} />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-10 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full border border-surface-border text-xl text-neutral-600">
                ⌕
              </span>
              <p className="text-sm text-neutral-500">
                왼쪽에서 기업을 검색해 선택하면 스코어와 차트가 표시됩니다.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
