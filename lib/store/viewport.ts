import { create } from "zustand";

export interface Viewport {
  longitude: number;
  latitude: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

export interface ViewportStore extends Viewport {
  basemap: "light" | "dark" | "satellite" | "streets";
  setViewport: (v: Partial<Viewport>) => void;
  setBasemap: (b: ViewportStore["basemap"]) => void;
}

// VT + NV pilot — center between them
const INITIAL: Viewport = {
  longitude: -100,
  latitude: 40,
  zoom: 4,
  bearing: 0,
  pitch: 0,
};

export const useViewportStore = create<ViewportStore>((set) => ({
  ...INITIAL,
  basemap: "dark",
  setViewport: (v) => set((s) => ({ ...s, ...v })),
  setBasemap: (basemap) => set({ basemap }),
}));
