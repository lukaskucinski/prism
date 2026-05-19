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

// VT pilot — center on Vermont
const INITIAL: Viewport = {
  longitude: -72.7,
  latitude: 44.1,
  zoom: 7.5,
  bearing: 0,
  pitch: 0,
};

export const useViewportStore = create<ViewportStore>((set) => ({
  ...INITIAL,
  basemap: "dark",
  setViewport: (v) => set((s) => ({ ...s, ...v })),
  setBasemap: (basemap) => set({ basemap }),
}));
