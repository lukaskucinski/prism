"use client";

import { COLOR_STOPS } from "@/lib/h3/colors";

export function Legend() {
  return (
    <div className="rounded-md border border-border bg-card/85 p-3 backdrop-blur-sm">
      <div className="mb-2 flex items-center justify-between gap-6">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Friction
        </span>
        <span className="text-[10px] text-muted-foreground">
          composite score 0–100
        </span>
      </div>
      <div
        className="h-3 w-56 rounded-sm border border-border/60"
        style={{
          background: `linear-gradient(to right, ${COLOR_STOPS.map(
            (s) => `${s.hex} ${s.score}%`
          ).join(", ")})`,
        }}
        aria-label="Friction color ramp"
      />
      <div className="mt-1 flex w-56 justify-between text-[10px] text-muted-foreground">
        {COLOR_STOPS.map((s) => (
          <span key={s.score}>{s.score}</span>
        ))}
      </div>
      <div className="mt-1 flex w-56 justify-between text-[10px] text-foreground/80">
        {COLOR_STOPS.map((s) => (
          <span key={s.label}>{s.label.split(" ")[0]}</span>
        ))}
      </div>
    </div>
  );
}
