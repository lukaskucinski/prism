"use client";

import { useEffect, useMemo, useState } from "react";
import { Layers, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  CATEGORY_LABELS,
  FRICTION_CATEGORIES,
  type FrictionCategory,
} from "@/lib/h3/categories";
import { cn } from "@/lib/utils";

interface Layer {
  layer_id: string;
  layer_name: string;
  friction_category: FrictionCategory;
  friction_tier: "high" | "medium" | "low" | null;
  ingest_status: "pending" | "success" | "partial" | "failed" | "skipped";
  feature_count: number | null;
  last_ingested: string | null;
}

const STATUS_COLOR: Record<Layer["ingest_status"], string> = {
  success: "bg-emerald-500/20 text-emerald-300",
  partial: "bg-amber-500/20 text-amber-300",
  failed: "bg-red-500/20 text-red-300",
  skipped: "bg-zinc-500/20 text-zinc-300",
  pending: "bg-blue-500/15 text-blue-300",
};

export function LayerPanel() {
  const [open, setOpen] = useState(false);
  const [layers, setLayers] = useState<Layer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || layers) return;
    fetch("/api/layers")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => setLayers(j.layers ?? []))
      .catch((e) => setError(String(e?.message ?? e)));
  }, [open, layers]);

  const grouped = useMemo(() => {
    const byCat: Record<string, Layer[]> = {};
    for (const cat of FRICTION_CATEGORIES) byCat[cat] = [];
    for (const l of layers ?? []) {
      (byCat[l.friction_category] ||= []).push(l);
    }
    return byCat;
  }, [layers]);

  const totals = useMemo(() => {
    const counts = { success: 0, failed: 0, skipped: 0, pending: 0, partial: 0 };
    for (const l of layers ?? []) counts[l.ingest_status] += 1;
    return counts;
  }, [layers]);

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        className="backdrop-blur-sm"
      >
        <Layers className="h-3.5 w-3.5" />
        Layers
      </Button>

      {open && (
        <div className="absolute right-4 top-16 z-20 max-h-[80vh] w-96 overflow-hidden rounded-md border border-border bg-card/95 shadow-xl backdrop-blur">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div>
              <div className="text-sm font-semibold">Layer catalog</div>
              {layers && (
                <div className="mt-0.5 flex flex-wrap gap-1 text-[10px]">
                  <StatusPill label="success" count={totals.success} />
                  <StatusPill label="partial" count={totals.partial} />
                  <StatusPill label="failed" count={totals.failed} />
                  <StatusPill label="skipped" count={totals.skipped} />
                  <StatusPill label="pending" count={totals.pending} />
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="max-h-[70vh] overflow-y-auto px-4 py-3">
            {error && (
              <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {error}
              </div>
            )}
            {!layers && !error && (
              <div className="text-xs text-muted-foreground">Loading layer catalog…</div>
            )}
            {layers && layers.length === 0 && (
              <div className="text-xs italic text-muted-foreground">
                No layers seeded yet. Run{" "}
                <code className="font-mono">python -m prism.seed.load_layers</code>.
              </div>
            )}
            {layers && layers.length > 0 && (
              <ul className="space-y-3">
                {FRICTION_CATEGORIES.map((cat) => {
                  const ls = grouped[cat];
                  if (!ls || ls.length === 0) return null;
                  return (
                    <li key={cat}>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        {CATEGORY_LABELS[cat]} ({ls.length})
                      </div>
                      <ul className="space-y-1">
                        {ls.map((l) => (
                          <li
                            key={l.layer_id}
                            className="flex items-start justify-between gap-2 rounded border border-border/60 bg-muted/20 px-2 py-1.5"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-xs font-medium" title={l.layer_name}>
                                {l.layer_name}
                              </div>
                              <div className="mt-0.5 text-[10px] text-muted-foreground">
                                {l.feature_count != null
                                  ? `${l.feature_count.toLocaleString()} features`
                                  : "—"}
                                {l.last_ingested && (
                                  <>
                                    {" · "}
                                    {new Date(l.last_ingested).toLocaleDateString()}
                                  </>
                                )}
                              </div>
                            </div>
                            <span
                              className={cn(
                                "shrink-0 rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wider",
                                STATUS_COLOR[l.ingest_status]
                              )}
                            >
                              {l.ingest_status}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function StatusPill({ label, count }: { label: keyof typeof STATUS_COLOR; count: number }) {
  if (count === 0) return null;
  return (
    <span className={cn("rounded px-1.5 py-0.5 uppercase tracking-wider", STATUS_COLOR[label])}>
      {label} {count}
    </span>
  );
}
