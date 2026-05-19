"use client";

import { useEffect, useRef, useState } from "react";
import mapboxgl, { type Map, type MapMouseEvent, type Popup } from "mapbox-gl";
import { useFilterStore } from "@/lib/store/filters";
import { useViewportStore } from "@/lib/store/viewport";
import { useUrlSync } from "@/lib/store/url-sync";
import { BASEMAPS } from "@/lib/map/basemaps";
import { tileUrlTemplate } from "@/lib/tiles/url";
import { mapboxFrictionExpression } from "@/lib/h3/colors";
import { HexLayer } from "./HexLayer";
import { BasemapSwitcher } from "./BasemapSwitcher";
import { Legend } from "@/components/panels/Legend";
import { HexTooltip } from "./HexTooltip";
import { HexPopup } from "./HexPopup";

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
if (MAPBOX_TOKEN) {
  mapboxgl.accessToken = MAPBOX_TOKEN;
}

interface HoveredHex {
  h3_index: string;
  friction_score: number;
  layer_count: number;
  top_friction_driver: string | null;
  x: number;
  y: number;
}

interface ClickedHex extends Omit<HoveredHex, "x" | "y"> {
  lng: number;
  lat: number;
}

export default function PrismMap() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const popupRef = useRef<Popup | null>(null);

  const viewport = useViewportStore();
  const filters = useFilterStore();

  const [hovered, setHovered] = useState<HoveredHex | null>(null);
  const [clicked, setClicked] = useState<ClickedHex | null>(null);
  const [styleReady, setStyleReady] = useState(false);

  useUrlSync();

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    if (!MAPBOX_TOKEN) {
      console.warn(
        "NEXT_PUBLIC_MAPBOX_TOKEN is not set; map will not render. " +
          "Set it in .env.local and restart."
      );
      return;
    }

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: BASEMAPS[viewport.basemap].styleUrl,
      center: [viewport.longitude, viewport.latitude],
      zoom: viewport.zoom,
      pitch: viewport.pitch,
      bearing: viewport.bearing,
      attributionControl: true,
      hash: false,
    });

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: false }), "bottom-right");
    map.addControl(new mapboxgl.GeolocateControl({ trackUserLocation: false }), "bottom-right");
    map.addControl(new mapboxgl.ScaleControl({ maxWidth: 120, unit: "imperial" }), "bottom-left");

    map.on("load", () => setStyleReady(true));
    map.on("style.load", () => setStyleReady(true));

    map.on("moveend", () => {
      const c = map.getCenter();
      useViewportStore.getState().setViewport({
        longitude: c.lng,
        latitude: c.lat,
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
      });
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Basemap switch
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    setStyleReady(false);
    map.setStyle(BASEMAPS[viewport.basemap].styleUrl);
  }, [viewport.basemap]);

  // Hex interactions
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleReady) return;

    const onMove = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ["prism-hex-fill"] });
      if (!features.length) {
        setHovered(null);
        map.getCanvas().style.cursor = "";
        return;
      }
      const f = features[0];
      const props = f.properties ?? {};
      map.getCanvas().style.cursor = "pointer";
      setHovered({
        h3_index: String(props.h3_index ?? ""),
        friction_score: Number(props.friction_score ?? 0),
        layer_count: Number(props.layer_count ?? 0),
        top_friction_driver: (props.top_friction_driver as string | null) ?? null,
        x: e.point.x,
        y: e.point.y,
      });
    };

    const onLeave = () => {
      setHovered(null);
      map.getCanvas().style.cursor = "";
    };

    const onClick = (e: MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ["prism-hex-fill"] });
      if (!features.length) return;
      const f = features[0];
      const props = f.properties ?? {};
      setClicked({
        h3_index: String(props.h3_index ?? ""),
        friction_score: Number(props.friction_score ?? 0),
        layer_count: Number(props.layer_count ?? 0),
        top_friction_driver: (props.top_friction_driver as string | null) ?? null,
        lng: e.lngLat.lng,
        lat: e.lngLat.lat,
      });
    };

    map.on("mousemove", onMove);
    map.on("mouseleave", onLeave);
    map.on("click", onClick);
    return () => {
      map.off("mousemove", onMove);
      map.off("mouseleave", onLeave);
      map.off("click", onClick);
    };
  }, [styleReady]);

  // Open Mapbox popup for clicked hex
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !clicked) {
      popupRef.current?.remove();
      popupRef.current = null;
      return;
    }
    const popup = new mapboxgl.Popup({ closeOnClick: false, maxWidth: "360px" })
      .setLngLat([clicked.lng, clicked.lat])
      .setHTML(`<div id="prism-popup-mount-${clicked.h3_index}"></div>`)
      .addTo(map);
    popup.on("close", () => setClicked(null));
    popupRef.current = popup;
    return () => {
      popup.remove();
    };
  }, [clicked]);

  return (
    <>
      <div ref={containerRef} className="absolute inset-0" />
      {styleReady && mapRef.current && (
        <HexLayer
          map={mapRef.current}
          tileUrl={tileUrlTemplate(filters)}
          paint={{
            "fill-color": mapboxFrictionExpression() as unknown as mapboxgl.ExpressionSpecification,
            "fill-opacity": 0.7,
            "fill-outline-color": "rgba(0,0,0,0.15)",
          }}
        />
      )}

      <header className="pointer-events-none absolute left-0 right-0 top-0 z-10 flex items-center justify-between p-4">
        <div className="pointer-events-auto rounded-md bg-card/80 px-3 py-2 backdrop-blur-sm border border-border">
          <span className="font-semibold tracking-tight">PRISM</span>
          <span className="ml-2 text-xs text-muted-foreground">
            Permitting Risk Index
          </span>
        </div>
        <div className="pointer-events-auto">
          <BasemapSwitcher />
        </div>
      </header>

      <div className="pointer-events-none absolute bottom-4 left-4 z-10">
        <div className="pointer-events-auto">
          <Legend />
        </div>
      </div>

      {hovered && !clicked && <HexTooltip data={hovered} />}
      {clicked && <HexPopup data={clicked} onClose={() => setClicked(null)} />}

      {!MAPBOX_TOKEN && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/95 p-8 text-center">
          <div className="max-w-md space-y-4">
            <h2 className="text-xl font-semibold">Mapbox token required</h2>
            <p className="text-sm text-muted-foreground">
              Set <code className="rounded bg-muted px-1.5 py-0.5">NEXT_PUBLIC_MAPBOX_TOKEN</code>{" "}
              in <code className="rounded bg-muted px-1.5 py-0.5">.env.local</code> and restart
              the dev server.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
