"use client";

import { useEffect, useRef, useState } from "react";
import { WS_BASE } from "../api";
import type { Candle } from "../types";

/**
 * 실시간 캔들 WebSocket 훅 (Phase 5/7).
 * 종목이 바뀌면 이전 연결을 반드시 정리한다 — 정리하지 않으면 구독이 누적된다.
 */
export function useRealtimeCandles(stockCode: string | null, enabled: boolean) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!stockCode || !enabled) return;

    const ws = new WebSocket(`${WS_BASE}/api/chart/ws/${stockCode}`);
    socketRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const candle = JSON.parse(event.data) as Candle;
      setCandles((prev) => {
        const last = prev[prev.length - 1];
        // 같은 구간이면 갱신, 새 구간이면 추가
        if (last && last.time === candle.time) {
          return [...prev.slice(0, -1), candle];
        }
        return [...prev, candle];
      });
    };

    return () => {
      ws.close();
      socketRef.current = null;
      setCandles([]);
      setConnected(false);
    };
  }, [stockCode, enabled]);

  return { candles, connected };
}
