"use client";

import { useState } from "react";

const MAX_SLOTS = 3;

/**
 * 기업 검색 + 관심종목 슬롯(0~3) 표시. Phase 7 에서 실제 검색/등록 API 와 연결한다.
 */
export default function CompanySelector({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (stockCode: string) => void;
}) {
  const [query, setQuery] = useState("");

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="기업명 또는 종목코드 검색"
        className="w-full rounded-md bg-neutral-900 px-3 py-2 text-sm outline-none ring-neutral-700 focus:ring-1"
      />

      <div className="mt-4 flex items-center gap-2 text-xs text-neutral-500">
        <span>관심종목 슬롯</span>
        {Array.from({ length: MAX_SLOTS }, (_, i) => (
          <span
            key={i}
            className="h-6 w-6 rounded border border-dashed border-neutral-700"
          />
        ))}
        <span>0 / {MAX_SLOTS}</span>
      </div>

      {selected && (
        <p className="mt-3 text-sm text-neutral-400">선택됨: {selected}</p>
      )}
    </div>
  );
}
