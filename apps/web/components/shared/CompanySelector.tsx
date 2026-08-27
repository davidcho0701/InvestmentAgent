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

  const isWatchlisted = (corpCode: string) => watchlist.some((w) => w.corp_code === corpCode);

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
    <div className="flex h-full flex-col">
      <div className="p-3">
        <div className="relative">
          <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-600">
            ⌕
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="종목명 또는 코드 검색"
            className="w-full rounded-md border border-surface-border bg-surface-raised py-2 pl-8 pr-3 text-sm text-neutral-100 outline-none placeholder:text-neutral-600 focus:border-accent/50 focus:ring-1 focus:ring-accent/30"
          />
        </div>

        {results && results.length > 0 && (
          <ul className="mt-2 max-h-64 space-y-0.5 overflow-y-auto rounded-md border border-surface-border bg-surface-raised p-1">
            {results.map((c) => (
              <li
                key={c.corp_code}
                className="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-overlay"
              >
                <button
                  type="button"
                  onClick={() => c.stock_code && onSelect(c.stock_code)}
                  className="min-w-0 flex-1 text-left"
                  disabled={!c.stock_code}
                >
                  <span className="truncate font-medium text-neutral-200">{c.corp_name}</span>
                  {c.stock_code && (
                    <span className="ml-1.5 font-mono text-[11px] tabular-nums text-neutral-600">
                      {c.stock_code}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => handleToggle(c)}
                  disabled={!isWatchlisted(c.corp_code) && watchlist.length >= MAX_SLOTS}
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-30 ${
                    isWatchlisted(c.corp_code)
                      ? "text-accent"
                      : "border border-surface-border text-neutral-400 hover:border-accent/40 hover:text-accent"
                  }`}
                >
                  {isWatchlisted(c.corp_code) ? "★ 등록됨" : "+ 등록"}
                </button>
              </li>
            ))}
          </ul>
        )}

        {actionError && <p className="mt-2 text-xs text-rose-400">{actionError}</p>}
      </div>

      <div className="flex items-center justify-between px-3 pb-2 pt-1">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
          관심종목
        </h3>
        <span className="font-mono text-[11px] tabular-nums text-neutral-600">
          {watchlist.length}/{MAX_SLOTS}
        </span>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {watchlist.length === 0 && (
          <p className="px-2 py-4 text-xs leading-5 text-neutral-600">
            검색해서 종목을 최대 3개까지 등록하면 실시간 모드로 전환돼요.
          </p>
        )}
        {watchlist.map((w) => {
          const isActive = selected === w.stock_code;
          return (
            <button
              key={w.corp_code}
              type="button"
              onClick={() => onSelect(w.stock_code)}
              className={`group flex w-full items-center justify-between rounded-md border px-2.5 py-2 text-left transition ${
                isActive
                  ? "border-accent/40 bg-accent/10"
                  : "border-transparent hover:border-surface-border hover:bg-surface-raised"
              }`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    isActive ? "bg-accent" : "bg-neutral-700"
                  }`}
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-neutral-200">
                    {w.corp_name}
                  </span>
                  <span className="block font-mono text-[11px] tabular-nums text-neutral-600">
                    {w.stock_code}
                  </span>
                </span>
              </span>
              <span
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  void remove(w.corp_code);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.stopPropagation();
                    void remove(w.corp_code);
                  }
                }}
                className="shrink-0 rounded px-1.5 py-0.5 text-xs text-neutral-600 opacity-0 transition hover:text-rose-400 group-hover:opacity-100"
                aria-label={`${w.corp_name} 관심종목 해제`}
              >
                ✕
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
