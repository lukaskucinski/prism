"use client";

import { useEffect, useState } from "react";
import { tierForScore, COLOR_STOPS } from "@/lib/h3/colors";
import { CATEGORY_LABELS, type FrictionCategory } from "@/lib/h3/categories";
import { X } from "lucide-react";

interface HexPopupProps {
  data: {
    h3_index: string;
    friction_score: number;
    layer_count: number;
    top_friction_driver: string | null;
    lng: number;
    lat: number;
  };
  onClose: () => void;
}

interface LayerDetail {
  layer_id: string;
  layer_name: string;
  friction_category: FrictionCategory;
  friction_weight: number;
  friction_tier: "high" | "medium" | "low" | null;
  agency_name: string | null;
  agency_url: string | null;
  permit_start_url: string | null;
}

interface HexDetailResponse {
  h3_index: string;
  friction_score: number;
  layer_count: number;
  layers: LayerDetail[];
}

/**
 * Renders inside the Mapbox popup container by portal-into-DOM. PrismMap
 * inserts a placeholder div with id="prism-popup-mount-{h3_index}"; this
 * component mounts there.
 */
export function HexPopup({ data, onClose }: HexPopupProps) {
  const [detail, setDetail] = useState<HexDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mountEl, setMountEl] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const el = document.getElementById(`prism-popup-mount-${data.h3_index}`);
    setMountEl(el);
  }, [data.h3_index]);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    fetch(`/api/hex/${encodeURIComponent(data.h3_index)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as HexDetailResponse;
      })
      .then((j) => {
        if (!cancelled) setDetail(j);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message ?? e));
      });
    return () => {
      cancelled = true;
    };
  }, [data.h3_index]);

  const tier = tierForScore(data.friction_score);
  const tierStop = COLOR_STOPS.find((s) => s.tier === tier)!;

  if (!mountEl) return null;

  // Portal via direct innerHTML manipulation is brittle; render React into the
  // mount element using a small wrapper. Next.js client component renders here.
  return (
    <Portal element={mountEl}>
      <div className="space-y-3 text-foreground">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-sm border border-border"
                style={{ background: tierStop.hex }}
              />
              <span className="text-sm font-semibold">{tierStop.label} friction</span>
              <span className="font-mono text-xs text-muted-foreground">
                {data.friction_score.toFixed(0)}
              </span>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {data.layer_count} layer{data.layer_count === 1 ? "" : "s"} · h3{" "}
              <code className="font-mono">{data.h3_index.slice(0, 10)}…</code>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {error && (
          <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            Couldn’t load layer detail: {error}
          </div>
        )}

        {!detail && !error && (
          <div className="text-xs text-muted-foreground">Loading layer breakdown…</div>
        )}

        {detail && detail.layers.length > 0 && (
          <ul className="-mx-1 max-h-72 space-y-1 overflow-y-auto px-1 text-xs">
            {detail.layers.map((l) => (
              <li key={l.layer_id} className="rounded border border-border/60 bg-muted/30 p-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium">{l.layer_name}</span>
                  {l.friction_tier && (
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[10px] uppercase tracking-wider"
                      style={{
                        background:
                          l.friction_tier === "high"
                            ? "rgba(237,105,37,0.2)"
                            : l.friction_tier === "medium"
                            ? "rgba(252,255,164,0.2)"
                            : "rgba(180,180,200,0.15)",
                      }}
                    >
                      {l.friction_tier}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {CATEGORY_LABELS[l.friction_category]}
                </div>
                {(l.agency_url || l.permit_start_url) && (
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                    {l.agency_url && (
                      <a
                        href={l.agency_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary underline-offset-2 hover:underline"
                      >
                        {l.agency_name ?? "agency"}
                      </a>
                    )}
                    {l.permit_start_url && (
                      <a
                        href={l.permit_start_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary underline-offset-2 hover:underline"
                      >
                        start permit →
                      </a>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Portal>
  );
}

function Portal({ element, children }: { element: HTMLElement; children: React.ReactNode }) {
  // We can't use ReactDOM.createPortal in a server-compatible way without
  // importing react-dom directly; do it at module level.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { createPortal } = require("react-dom") as typeof import("react-dom");
  return createPortal(children, element);
}
