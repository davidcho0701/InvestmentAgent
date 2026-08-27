"use client";

import useSWR from "swr";
import { ApiError, fetcher, post } from "@/lib/api";
import type { NewsEvidenceRefreshResponse, NewsEvidenceResponse } from "@/lib/types";
import { useState } from "react";

const scoreFmt = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});

function formatDate(value: string | null): string {
  if (!value) return "일자 없음";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function sentimentTone(score: number | null): string {
  if (score === null) return "text-neutral-500";
  if (score > 0.15) return "text-up";
  if (score < -0.15) return "text-down";
  return "text-neutral-500";
}

export default function LlmNewsEvidence({ stockCode }: { stockCode: string }) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  const { data, error, isLoading, mutate } = useSWR<NewsEvidenceResponse>(
    `/api/news-evidence/${stockCode}`,
    fetcher,
    {
      refreshInterval: 120_000,
      revalidateOnFocus: false,
    },
  );

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshMessage(null);
    try {
      const refreshed = await post<NewsEvidenceRefreshResponse>(
        `/api/news-evidence/${stockCode}/refresh`,
        {},
      );
      await mutate();
      setRefreshMessage(
        `수집 ${refreshed.result.collected} · 저장 ${refreshed.result.saved} · 고영향 ${refreshed.result.high_impact}`,
      );
    } catch (e) {
      setRefreshMessage(
        e instanceof ApiError ? e.message : "뉴스 근거 갱신에 실패했습니다.",
      );
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-panel">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-neutral-50">LLM 뉴스 근거</h2>
          <p className="mt-0.5 text-xs text-neutral-600">고영향 뉴스 자동 요약</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="hidden rounded-full border border-accent/20 bg-accent/10 px-2.5 py-1 text-[11px] font-medium text-accent sm:inline-flex">
            Ollama
          </span>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="rounded-md border border-surface-border bg-surface-raised px-2.5 py-1 text-[11px] font-medium text-neutral-300 transition hover:border-accent/40 hover:text-accent disabled:cursor-wait disabled:opacity-50"
          >
            {refreshing ? "갱신 중" : "뉴스 갱신"}
          </button>
        </div>
      </header>

      {isLoading && <p className="mt-4 text-sm text-neutral-500">뉴스 근거를 불러오는 중입니다.</p>}
      {error && <p className="mt-4 text-sm text-rose-400">뉴스 근거를 불러오지 못했습니다.</p>}
      {refreshMessage && (
        <p className="mt-3 font-mono text-[11px] tabular-nums text-neutral-600">
          {refreshMessage}
        </p>
      )}

      {!isLoading && !error && data?.items.length === 0 && (
        <p className="mt-4 rounded-lg border border-surface-border bg-surface-raised/50 p-3 text-sm text-neutral-600">
          최근 LLM 뉴스 근거 없음
        </p>
      )}

      {data && data.items.length > 0 && (
        <div className="mt-4 space-y-2">
          {data.items.map((item, index) => (
            <article
              key={`${item.url ?? item.title ?? "news"}-${index}`}
              className="rounded-lg border border-surface-border bg-surface-raised/60 p-3"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-neutral-600">
                <span>{formatDate(item.published_at)}</span>
                <span className="text-neutral-700">·</span>
                <span className={`font-mono tabular-nums ${sentimentTone(item.sentiment_score)}`}>
                  감성 {item.sentiment_score === null ? "없음" : scoreFmt.format(item.sentiment_score)}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-neutral-300">{item.evidence}</p>
              {item.title && (
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-neutral-500">
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer" className="hover:text-accent">
                      {item.title}
                    </a>
                  ) : (
                    item.title
                  )}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
