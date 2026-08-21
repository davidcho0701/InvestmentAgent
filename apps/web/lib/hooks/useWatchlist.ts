"use client";

import useSWR from "swr";
import { del, fetcher, post } from "../api";
import type { WatchlistItem } from "../types";

// TODO: 실제 로그인 붙기 전까지 데모용 고정 사용자 ID (useScorePolling 과 동일 관례).
const USER_ID = "demo-user";

/**
 * 관심종목 CRUD 훅. 슬롯 초과(409) 등 에러는 호출부에서 add()/remove() 의 반려로 처리한다.
 */
export function useWatchlist() {
  const { data, error, isLoading, mutate } = useSWR<WatchlistItem[]>(
    `/api/watchlist?user_id=${USER_ID}`,
    fetcher,
  );

  async function add(corpCode: string) {
    await post(`/api/watchlist?user_id=${USER_ID}`, { corp_code: corpCode });
    await mutate();
  }

  async function remove(corpCode: string) {
    await del(`/api/watchlist/${corpCode}?user_id=${USER_ID}`);
    await mutate();
  }

  return { watchlist: data ?? [], error, isLoading, add, remove };
}
