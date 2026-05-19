"use client";

import { useEffect } from "react";
import { useFilterStore } from "./filters";
import { useViewportStore } from "./viewport";
import type { FrictionCategory } from "@/lib/h3/categories";
import { FRICTION_CATEGORIES } from "@/lib/h3/categories";

/**
 * Mirror Zustand state into the URL hash (#z=8&lng=-118.2&lat=39.5&...).
 * Two-way: on mount, hydrate stores from URL; on store changes, push to URL.
 */
export function useUrlSync() {
  const viewport = useViewportStore();
  const filters = useFilterStore();

  // Hydrate from URL once on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return;
    const params = new URLSearchParams(hash);

    const z = Number(params.get("z"));
    const lng = Number(params.get("lng"));
    const lat = Number(params.get("lat"));
    if (!Number.isNaN(z) && !Number.isNaN(lng) && !Number.isNaN(lat)) {
      viewport.setViewport({ zoom: z, longitude: lng, latitude: lat });
    }

    const basemap = params.get("base") as ViewportStoreBasemap | null;
    if (basemap && ["light", "dark", "satellite", "streets"].includes(basemap)) {
      viewport.setBasemap(basemap);
    }

    const states = params.get("states");
    if (states) filters.setStates(states.split(","));

    const score = params.get("score");
    if (score) {
      const [lo, hi] = score.split(",").map(Number);
      if (!Number.isNaN(lo) && !Number.isNaN(hi)) filters.setScoreRange([lo, hi]);
    }

    const cats = params.get("cats");
    if (cats) {
      const decoded = cats
        .split(",")
        .filter((c): c is FrictionCategory =>
          FRICTION_CATEGORIES.includes(c as FrictionCategory)
        );
      filters.setCategories(decoded);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Push store → URL on change (debounced via rAF)
  useEffect(() => {
    if (typeof window === "undefined") return;
    let raf = 0;
    const sync = () => {
      const params = new URLSearchParams();
      params.set("z", viewport.zoom.toFixed(2));
      params.set("lng", viewport.longitude.toFixed(4));
      params.set("lat", viewport.latitude.toFixed(4));
      if (viewport.basemap !== "dark") params.set("base", viewport.basemap);
      if (filters.states.length) params.set("states", filters.states.join(","));
      if (filters.scoreRange[0] !== 0 || filters.scoreRange[1] !== 100) {
        params.set("score", filters.scoreRange.join(","));
      }
      if (filters.categories.length) params.set("cats", filters.categories.join(","));
      const hash = `#${params.toString()}`;
      if (window.location.hash !== hash) {
        history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
      }
    };
    raf = requestAnimationFrame(sync);
    return () => cancelAnimationFrame(raf);
  }, [
    viewport.zoom,
    viewport.longitude,
    viewport.latitude,
    viewport.basemap,
    filters.states,
    filters.scoreRange,
    filters.categories,
  ]);
}

type ViewportStoreBasemap = "light" | "dark" | "satellite" | "streets";
