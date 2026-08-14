"use client";

import { useState } from "react";
import CompanySelector from "@/components/shared/CompanySelector";
import FundamentalReport from "@/components/part1/FundamentalReport";
import ChartLiteracy from "@/components/part2/ChartLiteracy";

export default function DashboardPage() {
  const [stockCode, setStockCode] = useState<string | null>(null);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-bold">대시보드</h1>

      <div className="mt-6">
        <CompanySelector onSelect={setStockCode} selected={stockCode} />
      </div>

      {stockCode ? (
        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          <FundamentalReport stockCode={stockCode} />
          <ChartLiteracy stockCode={stockCode} />
        </div>
      ) : (
        <p className="mt-8 text-neutral-500">기업을 검색해 선택하세요.</p>
      )}
    </main>
  );
}
