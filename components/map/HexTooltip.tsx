"use client";

import { tierForScore, COLOR_STOPS } from "@/lib/h3/colors";

interface HexTooltipProps {
  data: {
    h3_index: string;
    friction_score: number;
    layer_count: number;
    top_friction_driver: string | null;
    x: number;
    y: number;
  };
}

export function HexTooltip({ data }: HexTooltipProps) {
  const tier = tierForScore(data.friction_score);
  const tierStop = COLOR_STOPS.find((s) => s.tier === tier)!;
  const left = Math.min(data.x + 16, (typeof window !== "undefined" ? window.innerWidth : 800) - 240);
  const top = Math.max(data.y - 60, 12);

  return (
    <div
      className="pointer-events-none absolute z-20 min-w-56 max-w-72 rounded-md border border-border bg-card/95 px-3 py-2 text-xs shadow-lg backdrop-blur"
      style={{ left, top }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-3 w-3 rounded-sm border border-border"
            style={{ background: tierStop.hex }}
            aria-hidden
          />
          <span className="font-medium">{tierStop.label} friction</span>
        </div>
        <span className="font-mono text-muted-foreground">
          {data.friction_score.toFixed(0)}
        </span>
      </div>
      <div className="mt-1.5 text-muted-foreground">
        {data.layer_count} layer{data.layer_count === 1 ? "" : "s"}
        {data.top_friction_driver ? (
          <>
            {" · top: "}
            <span className="text-foreground">{data.top_friction_driver}</span>
          </>
        ) : null}
      </div>
    </div>
  );
}
