"use client";

import useSWR from "swr";
import { fetcher } from "../api";
import type { ScoreResponse } from "../types";

/**
 * 스코어 조회 훅. 관심종목 여부에 따른 라이브/스냅샷 분기는 백엔드가 처리하므로
 * 프론트는 응답의 mode 필드로 배지만 구분해 표시한다.
 * 스냅샷 모드에서는 폴링이 무의미하므로 갱신을 끈다.
 */
export function useScorePolling(stockCode: string | null, userId: string) {
  const key = stockCode ? `/api/score/${stockCode}?user_id=${userId}` : null;

  const { data, error, isLoading, mutate } = useSWR<ScoreResponse>(key, fetcher, {
    refreshInterval: (latest) => (latest?.mode === "live" ? 60_000 : 0),
    revalidateOnFocus: false,
  });

  return { score: data, error, isLoading, refresh: mutate };
}
