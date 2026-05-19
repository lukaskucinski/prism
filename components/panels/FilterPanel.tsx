"use client";

import { useState } from "react";
import { Filter, X } from "lucide-react";
import { useFilterStore, filterHash } from "@/lib/store/filters";
import { GeographyFilter } from "@/components/filters/GeographyFilter";
import { ScoreFilter } from "@/components/filters/ScoreFilter";
import { CategoryFilter } from "@/components/filters/CategoryFilter";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function FilterPanel() {
  const [open, setOpen] = useState(false);
  const filters = useFilterStore();
  const hash = filterHash(filters);
  const activeCount =
    filters.states.length +
    filters.counties.length +
    filters.districts.length +
    filters.categories.length +
    (filters.scoreRange[0] !== 0 || filters.scoreRange[1] !== 100 ? 1 : 0);

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "backdrop-blur-sm",
          activeCount > 0 && "ring-1 ring-primary/40"
        )}
      >
        <Filter className="h-3.5 w-3.5" />
        Filters
        {activeCount > 0 && (
          <span className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
            {activeCount}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-4 top-16 z-20 w-80 rounded-md border border-border bg-card/95 p-4 shadow-xl backdrop-blur">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold">Filters</span>
            <div className="flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => filters.reset()}
                className="text-[11px]"
              >
                reset all
              </Button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className="space-y-4">
            <GeographyFilter />
            <div className="border-t border-border" />
            <ScoreFilter />
            <div className="border-t border-border" />
            <CategoryFilter />
          </div>

          <div className="mt-3 truncate text-[9px] font-mono text-muted-foreground" title={hash}>
            {hash}
          </div>
        </div>
      )}
    </>
  );
}
