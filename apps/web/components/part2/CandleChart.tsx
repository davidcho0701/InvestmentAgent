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
        background: { type: ColorType.Solid, color: "#171717" },
        textColor: "#d4d4d4",
      },
      grid: {
        vertLines: { color: "#262626" },
        horzLines: { color: "#262626" },
      },
      rightPriceScale: { borderColor: "#404040" },
      timeScale: { borderColor: "#404040", timeVisible: true, secondsVisible: false },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#f87171",
      downColor: "#60a5fa",
      borderVisible: false,
      wickUpColor: "#f87171",
      wickDownColor: "#60a5fa",
    });
    const volumeSeries = chart.addHistogramSeries({
      color: "#737373",
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
          color: candle.close >= candle.open ? "#ef444480" : "#3b82f680",
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

  return <div ref={containerRef} aria-label="OHLCV candlestick chart" className="mt-4 w-full" />;
}
