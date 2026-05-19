"use client";

import { useEffect } from "react";
import type { Map, FillLayerSpecification } from "mapbox-gl";

interface HexLayerProps {
  map: Map;
  tileUrl: string;
  paint: NonNullable<FillLayerSpecification["paint"]>;
  sourceLayer?: string;
  minzoom?: number;
  maxzoom?: number;
}

const SOURCE_ID = "prism-hex";
const FILL_LAYER_ID = "prism-hex-fill";
const LINE_LAYER_ID = "prism-hex-line";

/**
 * Mounts the PRISM vector-tile source + fill/line layers on the given Mapbox
 * map. Idempotent — safe to remount after style changes. Updates source URL
 * when the tileUrl prop changes.
 */
export function HexLayer({
  map,
  tileUrl,
  paint,
  sourceLayer = "hex",
  minzoom = 0,
  maxzoom = 22,
}: HexLayerProps) {
  useEffect(() => {
    const ensure = () => {
      if (!map.isStyleLoaded()) return false;

      const existingSource = map.getSource(SOURCE_ID);
      if (existingSource && "tiles" in existingSource) {
        // Update URL without re-creating layers (Mapbox lacks public setTiles;
        // remove + re-add when URL changes)
        const currentTiles = (existingSource as unknown as { tiles?: string[] }).tiles;
        if (currentTiles?.[0] === tileUrl) return true;
        if (map.getLayer(LINE_LAYER_ID)) map.removeLayer(LINE_LAYER_ID);
        if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID);
        map.removeSource(SOURCE_ID);
      }

      map.addSource(SOURCE_ID, {
        type: "vector",
        tiles: [tileUrl],
        minzoom,
        maxzoom,
      });

      map.addLayer({
        id: FILL_LAYER_ID,
        type: "fill",
        source: SOURCE_ID,
        "source-layer": sourceLayer,
        paint,
      });

      map.addLayer({
        id: LINE_LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        "source-layer": sourceLayer,
        paint: {
          "line-color": "rgba(255,255,255,0.18)",
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0, 8, 0.5, 12, 1],
        },
      });

      return true;
    };

    if (!ensure()) {
      const handler = () => {
        if (ensure()) map.off("styledata", handler);
      };
      map.on("styledata", handler);
      return () => {
        map.off("styledata", handler);
      };
    }

    return () => {
      if (map.getLayer(LINE_LAYER_ID)) map.removeLayer(LINE_LAYER_ID);
      if (map.getLayer(FILL_LAYER_ID)) map.removeLayer(FILL_LAYER_ID);
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
  }, [map, tileUrl, sourceLayer, minzoom, maxzoom, paint]);

  return null;
}
