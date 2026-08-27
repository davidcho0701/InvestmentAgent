"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { Candle, ChartAnnotation } from "@/lib/types";

type Props = {
  candles: Candle[];
  annotations: ChartAnnotation[];
};

/** A compact OHLCV view with markers that open the explanation cards below. */
export default function CandleChart({ candles, annotations }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "#0b0e13" },
        textColor: "#8a94a3",
        fontFamily: "var(--font-manrope), var(--font-plex-kr), ui-sans-serif, sans-serif",
      },
      grid: {
        vertLines: { color: "#171c25" },
        horzLines: { color: "#171c25" },
      },
      rightPriceScale: { borderColor: "#1f2530" },
      timeScale: { borderColor: "#1f2530", timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: "#2dd4bf40", labelBackgroundColor: "#11151c" },
        horzLine: { color: "#2dd4bf40", labelBackgroundColor: "#11151c" },
      },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#f43f5e",
      downColor: "#3b82f6",
      borderVisible: false,
      wickUpColor: "#f43f5e",
      wickDownColor: "#3b82f6",
    });
    const volumeSeries = chart.addHistogramSeries({
      color: "#3f4757",
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!candleSeries || !volumeSeries) return;

    candleSeries.setData(
      candles.map(
        (candle): CandlestickData<Time> => ({
          time: candle.time as Time,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        }),
      ),
    );
    volumeSeries.setData(
      candles.map(
        (candle): HistogramData<Time> => ({
          time: candle.time as Time,
          value: candle.volume,
          color: candle.close >= candle.open ? "#f43f5e80" : "#3b82f680",
        }),
      ),
    );
    candleSeries.setMarkers(
      annotations.map((annotation) => ({
        time: annotation.ts as Time,
        position: "aboveBar" as const,
        color: "#fbbf24",
        shape: "circle" as const,
        text: annotation.pattern_label,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [annotations, candles]);

  return <div ref={containerRef} aria-label="OHLCV candlestick chart" className="w-full" />;
}
