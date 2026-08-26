"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { ApiError, fetcher } from "@/lib/api";
import { useWatchlist } from "@/lib/hooks/useWatchlist";
import type { CompanySearchResult } from "@/lib/types";

const MAX_SLOTS = 3;

/**
 * 기업 검색 + 관심종목 슬롯(0~3) 표시/등록/해제.
 * Part1(FundamentalReport)과 Part2(ChartLiteracy)가 같은 selected(stockCode) 상태를 공유한다 (§9).
 */
export default function CompanySelector({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (stockCode: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const { watchlist, add, remove } = useWatchlist();

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const { data: results } = useSWR<CompanySearchResult[]>(
    debounced ? `/api/companies/search?q=${encodeURIComponent(debounced)}` : null,
    fetcher,
  );

  const isWatchlisted = (corpCode: string) =>
    watchlist.some((w) => w.corp_code === corpCode);

  async function handleToggle(company: CompanySearchResult) {
    setActionError(null);
    try {
      if (isWatchlisted(company.corp_code)) {
        await remove(company.corp_code);
      } else {
        await add(company.corp_code);
      }
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "요청 처리 중 오류가 발생했어요.");
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="기업명 또는 종목코드 검색"
        className="w-full rounded-md bg-neutral-900 px-3 py-2 text-sm outline-none ring-neutral-700 focus:ring-1"
      />

      {results && results.length > 0 && (
        <ul className="mt-2 divide-y divide-neutral-800 rounded-md border border-neutral-800">
          {results.map((c) => (
            <li key={c.corp_code} className="flex items-center justify-between px-3 py-2 text-sm">
              <button
                type="button"
                onClick={() => c.stock_code && onSelect(c.stock_code)}
                className="text-left hover:text-neutral-200"
                disabled={!c.stock_code}
              >
                <span className="font-medium">{c.corp_name}</span>
                {c.stock_code && (
                  <span className="ml-2 text-xs text-neutral-500">{c.stock_code}</span>
                )}
              </button>
              <button
                type="button"
                onClick={() => handleToggle(c)}
                disabled={!isWatchlisted(c.corp_code) && watchlist.length >= MAX_SLOTS}
                className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 disabled:opacity-40"
              >
                {isWatchlisted(c.corp_code) ? "관심종목 해제" : "관심종목 등록"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {actionError && <p className="mt-2 text-xs text-red-400">{actionError}</p>}

      <div className="mt-4 flex items-center gap-2 text-xs text-neutral-500">
        <span>관심종목 슬롯</span>
        {Array.from({ length: MAX_SLOTS }, (_, i) => (
          <span
            key={i}
            className={`h-6 w-6 rounded border ${
              i < watchlist.length
                ? "border-emerald-600 bg-emerald-500/20"
                : "border-dashed border-neutral-700"
            }`}
          />
        ))}
        <span>
          {watchlist.length} / {MAX_SLOTS}
        </span>
      </div>

      {selected && <p className="mt-3 text-sm text-neutral-400">선택됨: {selected}</p>}
    </div>
  );
}
