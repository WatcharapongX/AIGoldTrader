'use client';

import { CandlestickSeries, ColorType, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import type { Candle } from '@/types/market.generated';

function point(candle: Candle) {
  return {
    time: Date.parse(candle.open_time) / 1000 as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  };
}

export function RealtimeMarketChart({ candles }: { candles: Candle[] }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const fittedLength = useRef(0);

  useEffect(() => {
    if (!container.current) return;
    const value = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#0a0f1a' },
        textColor: '#8898ae',
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: '#172130' },
        horzLines: { color: '#172130' },
      },
      rightPriceScale: {
        borderColor: '#253044',
        scaleMargins: { top: 0.12, bottom: 0.1 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#253044',
        rightOffset: 8,
      },
      crosshair: {
        vertLine: { color: '#73839a' },
        horzLine: { color: '#73839a' },
      },
    });
    const valueSeries = value.addSeries(CandlestickSeries, {
      upColor: '#36c4a4',
      downColor: '#ed7a88',
      wickUpColor: '#36c4a4',
      wickDownColor: '#ed7a88',
      borderVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    chart.current = value;
    series.current = valueSeries;
    return () => {
      series.current = null;
      chart.current = null;
      value.remove();
    };
  }, []);

  useEffect(() => {
    if (!series.current) return;
    series.current.setData(candles.map(point));
    if (candles.length && fittedLength.current !== candles.length) {
      chart.current?.timeScale().fitContent();
      fittedLength.current = candles.length;
    }
  }, [candles]);

  return (
    <div
      ref={container}
      className="h-full min-h-[260px] w-full"
      aria-label="กราฟแท่งเทียน XAUUSD M5 จากผู้ให้บริการ"
      role="img"
    />
  );
}
