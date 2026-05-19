# Frontend

Next.js 16 App Router. React 19 strict. Tailwind v4. Mapbox GL JS 3.18+. Zustand for state. Single-page map at `/`.

## Dev server

```powershell
pnpm dev -p 3001
```

**Port 3001, not 3000.** Port 3000 is occupied by the HSNV3 portal dev server on this machine. `localhost:3001` is added to the Mapbox token's URL allowlist.

If hot-reload doesn't pick up an `.env` change (e.g. `NEXT_PUBLIC_TILE_VERSION`), kill and restart — `NEXT_PUBLIC_*` vars are inlined into the client bundle at start.

## Three painful Mapbox traps

We hit all three in this session. Future you will hit them again if you forget.

### 1. Mapbox CSS overrides the container's `position`

Mapbox-GL's stylesheet sets `.mapboxgl-map { position: relative }`. If your container div is `position: absolute; inset: 0` (Tailwind `absolute inset-0`), Mapbox overrides position to `relative`, the `inset-0` rules no longer apply, the div collapses to content-size (height: 0), and the map is black.

**Fix:** make the container's size NOT depend on positioning. Use `h-full w-full` or inline `style={{ height: '100%', width: '100%' }}` on the container, and ensure the parent has a real height (e.g. `<main style={{ height: '100dvh' }}>`).

Located in `components/map/PrismMap.tsx`.

### 2. Tile URLs must be absolute, not relative

Mapbox GL fetches vector tiles in a **Web Worker**. Workers have no `window.location`, so `new Request("/api/tiles/...")` throws `Failed to parse URL`. You'll see the error in the browser console but it doesn't propagate to `map.on('error')` reliably.

**Fix:** prepend `window.location.origin` when building tile URLs on the client. See `lib/tiles/url.ts::tileUrlTemplate()`.

```ts
const base = origin ?? (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000");
return `${base}/api/tiles/v${TILE_VERSION}/{z}/{x}/{y}.mvt?f=${filterB64}`;
```

### 3. Memoize `paint` props on Mapbox layer wrappers

`HexLayer` has a `useEffect` that adds source + layers, with `paint` in its dep array. If `paint` is a fresh object literal on every parent render (e.g. inline `paint={{ "fill-color": ... }}`), the effect re-runs every render. It removes and re-adds the source/layer. During the brief gap, `queryRenderedFeatures` in mousemove/click handlers throws `The layer 'prism-hex-fill' does not exist`.

**Fix:** `useMemo(() => ({ ... }), [])` both `paint` and `tileUrl` in `PrismMap.tsx`, then pass the memoized refs to `HexLayer`.

Also guard query handlers:

```ts
if (!map.getLayer("prism-hex-fill")) return [];
return map.queryRenderedFeatures(point, { layers: ["prism-hex-fill"] });
```

## App structure

```
app/
├── layout.tsx                    # next-themes provider, dark default
├── page.tsx                      # <main h-100dvh w-100vw><PrismMapClient /></main>
├── globals.css                   # Tailwind v4 import + @theme tokens + Mapbox CSS
└── api/
    ├── tiles/[v]/[z]/[x]/[y]/route.ts   # Calls prism_get_hex_mvt RPC, returns MVT bytes
    ├── hex/[h3_index]/route.ts          # Joins prism_hex_layer × prism_layers for popup
    ├── layers/route.ts                   # Catalog of layers with status
    ├── states/route.ts
    ├── counties/route.ts                 # ?states=50,32
    └── districts/route.ts

components/
├── map/
│   ├── PrismMapClient.tsx        # Thin client wrapper around dynamic-imported PrismMap
│   ├── PrismMap.tsx              # Main map. Singleton Mapbox instance. Hover/click handlers.
│   ├── HexLayer.tsx              # Idempotent source+layer registration
│   ├── HexTooltip.tsx, HexPopup.tsx
│   └── BasemapSwitcher.tsx
├── filters/{Geography,Score,Category}Filter.tsx
├── panels/{Legend,FilterPanel,LayerPanel}.tsx
└── ui/                           # shadcn primitives (button, slider, checkbox, popover)

lib/
├── store/{filters,viewport,url-sync}.ts   # Zustand
├── h3/{resolution,colors,categories}.ts
├── tiles/url.ts                  # tileUrlTemplate (absolute origin!)
├── map/basemaps.ts
├── supabase/{client,server}.ts
└── utils.ts                      # `cn()` for class merging
```

## State management

Zustand. Two stores, no provider:
- `useFilterStore`: states[], counties[], districts[], scoreRange, categories[], customPolygon
- `useViewportStore`: longitude, latitude, zoom, bearing, pitch, basemap

URL hash mirrors state via `useUrlSync()` so links are shareable. Format:

```
http://localhost:3001/#z=7.5&lng=-72.7&lat=44.1&base=dark&states=VT&score=20,80&cats=critical_habitat,floodplain_wetland
```

Hydrates on mount, then writes back on every state change (debounced via rAF).

## Mapbox initialization

`PrismMap.tsx` creates a singleton mapboxgl.Map in a `useEffect` keyed on `[]`. On `moveend` it pushes viewport back to Zustand. On `basemap` change (Zustand), it calls `map.setStyle()`, which triggers `style.load` re-add of the hex source+layer.

Mapbox token is read at module load from `process.env.NEXT_PUBLIC_MAPBOX_TOKEN`. Allowlist for the public token includes `http://localhost:3000/` and `http://localhost:3001/`.

## Color ramp

`lib/h3/colors.ts` defines the magma-style stops:

| Score | Color | Tier |
|---|---|---|
| 0 | `#1a0b30` (deep purple) | Minimal |
| 25 | `#4a0d67` (magenta-purple) | Low |
| 50 | `#b73779` (red-magenta) | Moderate |
| 75 | `#ed6925` (orange) | High |
| 100 | `#fcffa4` (bright yellow) | Very High |

`mapboxFrictionExpression()` produces the Mapbox `["interpolate", ["linear"], ...]` paint expression. Hex `fill-opacity` is 0.7 so the basemap shows through.

## Filters

Filter state propagates to tiles via `filterHash(state)` → base64url → URL query `?f=...`. The Postgres function decodes the JSONB and applies WHERE clauses against the hex tables.

Custom polygon upload (file parsers in `lib/file-parsers.ts`, lifted from PEIT) is wired for Phase 3 — geometry filtering happens client-side after fetch.

## Debugging the map

If you see a black map or missing hexes, hit these checks in order:

1. **Browser console** — `[PrismMap] init { ... }` log line shows token, container size, mapbox version. If `containerSize: "WxH"` has H=0, you've hit trap #1 (or parent has no height).
2. **Network tab** — search for `mapbox.com` and `localhost:3001/api/tiles`. 401 on mapbox = token issue. 404 on /api/tiles = route or RPC issue.
3. **`map.on('error')` handler** — wired in PrismMap, surfaces every Mapbox error to console (normally swallowed). Look for `[PrismMap] Mapbox error:` lines.
4. **DB sanity** — `curl http://localhost:3001/api/tiles/v2/10/305/372.mvt -o /tmp/t.mvt && file /tmp/t.mvt`. Should be > 1KB binary data. If 0 bytes, scorer hasn't run yet, R7/R6 are empty, or no hexes intersect the tile.

## Build

`pnpm build` does a full production build via Turbopack. We've validated it green; CI is not yet wired (manual deploy to Vercel via the dashboard).
