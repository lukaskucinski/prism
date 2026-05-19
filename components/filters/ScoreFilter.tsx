"use client";

import { Slider } from "@/components/ui/slider";
import { useFilterStore } from "@/lib/store/filters";
import { tierForScore, COLOR_STOPS } from "@/lib/h3/colors";

export function ScoreFilter() {
  const scoreRange = useFilterStore((s) => s.scoreRange);
  const setScoreRange = useFilterStore((s) => s.setScoreRange);
  const [lo, hi] = scoreRange;
  const loTier = COLOR_STOPS.find((s) => s.tier === tierForScore(lo))!;
  const hiTier = COLOR_STOPS.find((s) => s.tier === tierForScore(hi))!;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground">Friction</span>
        <span className="font-mono text-foreground">
          <span style={{ color: loTier.hex }}>{lo}</span>
          <span className="mx-1 text-muted-foreground">–</span>
          <span style={{ color: hiTier.hex }}>{hi}</span>
        </span>
      </div>
      <Slider
        min={0}
        max={100}
        step={1}
        value={scoreRange}
        onValueChange={(v) => setScoreRange([v[0] ?? 0, v[1] ?? 100])}
      />
    </div>
  );
}
