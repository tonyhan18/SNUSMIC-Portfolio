"use client";

import { OverlayChart, type OverlaySeries } from "@/components/strategy/overlay-chart";

type EquityPoint = { date: string; nav: number };

function sampled(points: EquityPoint[]) {
  return points
    .filter((_, index) => index % 5 === 0 || index === points.length - 1)
    .map((point) => ({ time: point.date, value: point.nav }));
}

export function UsIndexMtfChart({
  symbol,
  strategy,
  benchmark,
}: {
  symbol: string;
  strategy: EquityPoint[];
  benchmark: EquityPoint[];
}) {
  const series: OverlaySeries[] = [
    { id: `${symbol}-strategy`, label: "MTF 전략", color: "stamp", width: 3, data: sampled(strategy) },
    { id: `${symbol}-buyhold`, label: "매수 후 보유", color: "#64748b", dashed: true, data: sampled(benchmark) },
  ];
  return (
    <OverlayChart
      series={series}
      valueFormatter={(value) => `${value.toFixed(2)}×`}
      logScale
      heightClass="h-[360px]"
      ariaLabel={`${symbol} 전략과 매수 후 보유 NAV`}
    />
  );
}
