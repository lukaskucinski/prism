import { create } from "zustand";
import type { FrictionCategory } from "@/lib/h3/categories";

export interface FilterState {
  states: string[];
  counties: string[];
  districts: string[];
  scoreRange: [number, number];
  categories: FrictionCategory[];
  customPolygon: GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon> | null;

  setStates: (states: string[]) => void;
  setCounties: (counties: string[]) => void;
  setDistricts: (districts: string[]) => void;
  setScoreRange: (range: [number, number]) => void;
  setCategories: (categories: FrictionCategory[]) => void;
  toggleCategory: (category: FrictionCategory) => void;
  setCustomPolygon: (poly: GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon> | null) => void;
  reset: () => void;
}

const INITIAL: Omit<
  FilterState,
  | "setStates"
  | "setCounties"
  | "setDistricts"
  | "setScoreRange"
  | "setCategories"
  | "toggleCategory"
  | "setCustomPolygon"
  | "reset"
> = {
  states: [],
  counties: [],
  districts: [],
  scoreRange: [0, 100],
  categories: [],
  customPolygon: null,
};

export const useFilterStore = create<FilterState>((set) => ({
  ...INITIAL,
  setStates: (states) => set({ states }),
  setCounties: (counties) => set({ counties }),
  setDistricts: (districts) => set({ districts }),
  setScoreRange: (scoreRange) => set({ scoreRange }),
  setCategories: (categories) => set({ categories }),
  toggleCategory: (category) =>
    set((s) => ({
      categories: s.categories.includes(category)
        ? s.categories.filter((c) => c !== category)
        : [...s.categories, category],
    })),
  setCustomPolygon: (customPolygon) => set({ customPolygon }),
  reset: () => set(INITIAL),
}));

/**
 * Stable cache key for the active filter set. Used to invalidate tile cache.
 * Drop customPolygon so it doesn't fragment the cache (polygon filtering
 * happens client-side after fetch).
 */
export function filterHash(state: FilterState): string {
  return JSON.stringify({
    s: [...state.states].sort(),
    c: [...state.counties].sort(),
    d: [...state.districts].sort(),
    r: state.scoreRange,
    g: [...state.categories].sort(),
  });
}
