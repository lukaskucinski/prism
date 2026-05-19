"use client";

import { BASEMAPS, type BasemapKey } from "@/lib/map/basemaps";
import { useViewportStore } from "@/lib/store/viewport";
import { cn } from "@/lib/utils";

const ORDER: BasemapKey[] = ["dark", "light", "streets", "satellite"];

export function BasemapSwitcher() {
  const basemap = useViewportStore((s) => s.basemap);
  const setBasemap = useViewportStore((s) => s.setBasemap);

  return (
    <div className="flex gap-1 rounded-md border border-border bg-card/80 p-1 backdrop-blur-sm">
      {ORDER.map((key) => {
        const b = BASEMAPS[key];
        const active = basemap === key;
        return (
          <button
            key={key}
            type="button"
            onClick={() => setBasemap(key)}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
            aria-pressed={active}
          >
            {b.name}
          </button>
        );
      })}
    </div>
  );
}
