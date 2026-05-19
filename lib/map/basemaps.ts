/**
 * Basemap registry. Match PEIT Map Creator's four-style set:
 * Street (OSM via Mapbox), Light, Dark, Satellite.
 *
 * Using Mapbox's hosted styles where available (token-gated, fine since the
 * token is public for client-side use). Light/dark match Kepler-style.
 */
export type BasemapKey = "light" | "dark" | "satellite" | "streets";

export interface Basemap {
  key: BasemapKey;
  name: string;
  styleUrl: string;
  /** Hex color shown behind tiles until they load. */
  background: string;
}

export const BASEMAPS: Record<BasemapKey, Basemap> = {
  dark: {
    key: "dark",
    name: "Dark",
    styleUrl: "mapbox://styles/mapbox/dark-v11",
    background: "#0a0a0a",
  },
  light: {
    key: "light",
    name: "Light",
    styleUrl: "mapbox://styles/mapbox/light-v11",
    background: "#e5e5e5",
  },
  satellite: {
    key: "satellite",
    name: "Satellite",
    styleUrl: "mapbox://styles/mapbox/satellite-streets-v12",
    background: "#000000",
  },
  streets: {
    key: "streets",
    name: "Streets",
    styleUrl: "mapbox://styles/mapbox/streets-v12",
    background: "#f0eee6",
  },
};
