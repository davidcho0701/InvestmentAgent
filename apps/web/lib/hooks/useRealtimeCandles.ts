"use client";

import { useEffect, useRef, useState } from "react";
import { WS_BASE } from "../api";
import type { Candle, ChartAnnotation } from "../types";

type ChartStreamMessage =
  | { type: "candle"; candle: Candle }
  | { type: "annotations"; annotations: ChartAnnotation[] };

/**
 * Owns one browser WebSocket per selected live stock. The cleanup prevents
 * connections and listeners accumulating while the user changes companies.
 */
export function useRealtimeCandles(stockCode: string | null, enabled: boolean) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [annotations, setAnnotations] = useState<ChartAnnotation[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!stockCode || !enabled) {
      setCandles([]);
      setAnnotations([]);
      setConnected(false);
      return;
    }

    const ws = new WebSocket(`${WS_BASE}/api/chart/ws/${stockCode}`);
    socketRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data) as ChartStreamMessage | Candle;
      // Accept the early candle-only protocol as well as the typed protocol.
      if ("time" in message) {
        updateCandle(setCandles, message);
      } else if (message.type === "candle") {
        updateCandle(setCandles, message.candle);
      } else if (message.type === "annotations") {
        setAnnotations((previous) => mergeAnnotations(previous, message.annotations));
      }
    };

    return () => {
      ws.close();
      socketRef.current = null;
      setCandles([]);
      setAnnotations([]);
      setConnected(false);
    };
  }, [stockCode, enabled]);

  return { candles, annotations, connected };
}

function updateCandle(
  setCandles: React.Dispatch<React.SetStateAction<Candle[]>>,
  candle: Candle,
) {
  setCandles((previous) => {
    const index = previous.findIndex((item) => item.time === candle.time);
    if (index === -1) return [...previous, candle].sort((a, b) => a.time - b.time);
    const next = [...previous];
    next[index] = candle;
    return next;
  });
}

function mergeAnnotations(
  previous: ChartAnnotation[],
  received: ChartAnnotation[],
): ChartAnnotation[] {
  const byKey = new Map(
    previous.map((annotation) => [`${annotation.ts}-${annotation.pattern_label}`, annotation]),
  );
  for (const annotation of received) {
    byKey.set(`${annotation.ts}-${annotation.pattern_label}`, annotation);
  }
  return [...byKey.values()].sort((a, b) => a.ts - b.ts);
}
