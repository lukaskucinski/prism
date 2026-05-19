# PRISM — Permitting Risk Index & Spatial Model

## Project Overview

PRISM is a national-scale web mapping application that visualizes environmental and permitting complexity across the United States using an H3 hexagonal grid. Each hex tile is assigned a composite friction index derived from dozens of authoritative environmental, historic, and regulatory data layers. The result is a heat map that lets broadband deployers, state broadband offices, and permitting professionals instantly see where infrastructure projects will face high, medium, or low environmental review burden — before a single route is designed.

PRISM is designed as a standalone web map that will eventually integrate as a toggleable layer within the HexRoute application.

---

## Architecture & Tech Stack

PRISM must be built on the same stack as the existing HexRoute and PEIT Map Creator projects to ensure compatibility and code reuse.

### Frontend
- **Next.js 16** with App Router
- **React 19**
- **TypeScript** (strict mode)
- **Tailwind CSS v4** + PostCSS
- **shadcn/ui** (Radix UI primitives) for all UI components
- **Leaflet 1.9.4** + **React Leaflet 5.x** for map rendering
- **Lucide React** for icons
- **next-themes** for light/dark mode
- **Zod** for schema validation

### Backend / Infrastructure
- **Supabase** — PostgreSQL database with PostGIS extension for tile storage, hex index tables, user auth, and feature hosting
- **Modal.com** — serverless Python compute for data ingest pipelines, H3 indexing jobs, and paid analysis features (voronoi-based environmental project area generation)
- **Vercel** — frontend deployment with edge functions

### Geospatial Libraries
- **h3-js** (frontend) — H3 hex resolution rendering and coordinate conversion
- **h3** (Python, backend) — H3 indexing during data ingest pipeline
- **@turf/turf** — client-side geometry operations (bbox, intersect, area)
- **GeoPandas / Shapely / Fiona** (Python, Modal) — backend geospatial processing
- **shpjs, @tmcw/togeojson, jszip** — client-side geospatial file parsing (reuse PEIT patterns)

---

## Data Pipeline Architecture

This is the most critical part of the application. Get the data ingest, index creation, and tile generation right before investing in UI polish.

### Phase 1: Layer Ingest

Environmental and permitting layers are sourced from the APPEIT project's layer catalog. The catalog currently tracks **561 layers** (208 fully configured) across 48 host organizations, served as ESRI ArcGIS REST FeatureServer endpoints.

**Input:** `scan_aprx/layer_config_from_rest_noraw.json` from the APPEIT project contains the layer catalog with service URLs, layer IDs, geometry types, group categories, and symbology.

**Ingest pipeline (Modal.com Python job):**

1. Read the layer catalog JSON
2. For each layer:
   a. Query the ESRI REST endpoint using the POST-based query strategy from PEIT Map Creator's `arcgis_query.py` (handles pagination, envelope/polygon queries, timeout fallbacks)
   b. Convert ESRI JSON geometry responses to GeoJSON
   c. Store raw features in a Supabase staging table (or PostGIS)
   d. Log ingest metadata: feature count, geometry type, query method, any errors
3. Layers should be tagged with their environmental category (EPA Programs, Federal/Tribal Land, Floodplains, Critical Habitats, Historic Places, State Lands, Infrastructure, etc.)

**Layer update cadence:** Most federal layers update quarterly or annually. Build the pipeline to support incremental refresh per-layer with a `last_ingested` timestamp.

**Critical consideration:** The 561 layers span national coverage. For the initial build, prioritize the ~50 layers most relevant to NEPA Extraordinary Circumstances screening:
- USFWS Critical Habitat (final + proposed)
- National Wetlands Inventory
- FEMA Flood Hazard Zones
- National Register of Historic Places
- Tribal/AIAN Lands
- BLM/USFS/NPS Federal Lands
- EPA Superfund/RCRA/TRI sites
- Wild & Scenic Rivers
- Coastal Zone Management Areas
- Coastal Barrier Resources
- State Protected Lands
- Infrastructure corridors (pipelines, transmission lines)
- EPA EJScreen / CEJST environmental justice layers

### Phase 2: H3 Indexing

For each ingested layer, compute which H3 hexes at **resolution 9** (base resolution, ~0.11 km²) intersect the layer's features.

**Indexing pipeline (Modal.com Python job):**

1. For each layer, iterate through features
2. For polygon features: use `h3.polyfill()` to get all R9 hexes that fall within the polygon, plus `h3.compact()` for storage efficiency
3. For line features: buffer the line by an appropriate distance (e.g., 500ft for pipelines, 100ft for transmission lines) then polyfill
4. For point features: get the R9 hex containing the point, optionally buffer
5. Store the result as rows in a Supabase table: `(h3_index_r9, layer_id, layer_category, feature_count)`
6. Pre-aggregate to R8 and R7 using `h3.h3_to_parent()`:
   - R8 hex value = aggregation function over child R9 hexes (e.g., max friction, count of layers present, weighted sum)
   - R7 hex value = aggregation of child R8 hexes

**Output Supabase tables:**

```sql
-- Base resolution index
CREATE TABLE prism_hex_r9 (
  h3_index TEXT PRIMARY KEY,         -- H3 index string
  friction_score REAL,                -- Composite friction index (0-100)
  layer_count INTEGER,                -- Number of overlapping layers
  layer_ids TEXT[],                    -- Array of layer IDs present
  category_flags JSONB,               -- { "critical_habitat": true, "wetlands": false, ... }
  top_friction_driver TEXT,           -- Layer contributing most to score
  geom GEOMETRY(Polygon, 4326)        -- H3 hex boundary for spatial queries
);

-- Aggregated resolutions
CREATE TABLE prism_hex_r8 (
  h3_index TEXT PRIMARY KEY,
  friction_score REAL,
  layer_count INTEGER,
  layer_summary JSONB,
  geom GEOMETRY(Polygon, 4326)
);

CREATE TABLE prism_hex_r7 (
  h3_index TEXT PRIMARY KEY,
  friction_score REAL,
  layer_count INTEGER,
  layer_summary JSONB,
  geom GEOMETRY(Polygon, 4326)
);

-- Layer metadata
CREATE TABLE prism_layers (
  layer_id TEXT PRIMARY KEY,
  layer_name TEXT,
  category TEXT,
  source_url TEXT,
  geometry_type TEXT,
  feature_count INTEGER,
  friction_weight REAL,               -- Weight for composite scoring (set by evaluation task)
  friction_tier TEXT,                  -- 'high', 'medium', 'low' (set by evaluation task)
  agency_name TEXT,
  agency_url TEXT,                     -- Link to permitting agency
  permit_start_url TEXT,              -- Direct link to begin permitting process
  last_ingested TIMESTAMP,
  description TEXT
);

-- Spatial index for fast viewport queries
CREATE INDEX idx_prism_r9_geom ON prism_hex_r9 USING GIST (geom);
CREATE INDEX idx_prism_r8_geom ON prism_hex_r8 USING GIST (geom);
CREATE INDEX idx_prism_r7_geom ON prism_hex_r7 USING GIST (geom);

-- Filter indexes
CREATE INDEX idx_prism_r9_score ON prism_hex_r9 (friction_score);
```

### Phase 3: Tile Serving Strategy

**Performance is paramount.** The hex grid must render quickly and transition smoothly between resolutions as the user zooms.

**Approach: Pre-computed vector tiles served from Supabase/PostGIS via Supabase Edge Functions or a lightweight tile server.**

Zoom-to-resolution mapping:
| Map Zoom | H3 Resolution | Hex Count (CONUS) | Strategy |
|----------|--------------|-------------------|----------|
| 4-6      | R7           | ~50,000           | Serve all visible hexes in viewport via PostGIS spatial query |
| 7-9      | R8           | ~350,000          | Viewport-clipped spatial query |
| 10+      | R9           | ~2,400,000        | Viewport-clipped spatial query, mandatory geographic filter |

**Tile endpoint** (Supabase Edge Function or API route):
```
GET /api/tiles?z={zoom}&bbox={west,south,east,north}&state={optional}&county={optional}
```

Returns GeoJSON FeatureCollection of hex polygons within the viewport at the appropriate resolution, with `friction_score` and `layer_summary` as feature properties.

**Client-side rendering:**
- Use Leaflet's GeoJSON layer with style function that maps `friction_score` to a color ramp
- On zoom change: swap the GeoJSON layer to the appropriate resolution table
- Debounce `moveend` events to avoid excessive re-fetches
- Cache recently fetched tiles client-side in a Map/LRU cache keyed by viewport hash

**Alternative to evaluate:** If PostGIS spatial queries prove too slow at national scale, pre-generate PMTiles or MBTiles vector tile archives for each resolution and serve from Vercel Blob Storage or Supabase Storage. This trades freshness for performance — tiles regenerated on a schedule rather than live-queried.

---

## Friction Index

The composite friction score for each hex is derived from the environmental/permitting layers that intersect it. **A separate task will evaluate all layers and assign friction weights and tier classifications.** The PRISM data model must support this by:

1. Storing per-layer `friction_weight` (numeric) and `friction_tier` ('high', 'medium', 'low') in the `prism_layers` table
2. Computing the composite score per hex as a function of overlapping layer weights — the specific formula (weighted sum, max, tier-based, etc.) will be defined during the layer evaluation task
3. Supporting re-computation when weights change, without re-ingesting raw data
4. Exposing the layer breakdown per hex (which layers contribute, their individual weights) for transparency in the UI

**Placeholder scoring for initial development:** Until the layer evaluation task is complete, use a simple count-based proxy: `friction_score = min(100, layer_count * 10)`. This lets UI development proceed in parallel.

---

## UI/UX Design

The application must be **beautiful, modern, and sleek.** Take design cues from tools like Kepler.gl, Unfolded Studio, and Felt.com — clean dark map backgrounds, vibrant data visualization, minimal chrome, generous whitespace in panels.

### Layout

Full-viewport map with floating UI panels:

```
+-------------------------------------------------------+
|  [PRISM logo]  [Search]           [Filters] [Layers]  |
|                                                        |
|                                                        |
|                    MAP VIEWPORT                         |
|                                                        |
|                                                        |
|  +------------------+                                  |
|  | LEGEND           |                   [Zoom +/-]     |
|  | friction ramp    |                   [Geolocate]    |
|  | 0 ████████ 100   |                   [Draw/Upload]  |
|  +------------------+                                  |
+-------------------------------------------------------+
```

### Color Ramp

Use a diverging color ramp from cool (low friction) to hot (high friction):

| Score Range | Color | Label |
|-------------|-------|-------|
| 0-10        | #1a9850 (green) | Minimal |
| 11-25       | #91cf60 (light green) | Low |
| 26-50       | #fee08b (yellow) | Moderate |
| 51-75       | #fc8d59 (orange) | High |
| 76-100      | #d73027 (red) | Very High |

Hex opacity should be ~0.7 to let the basemap show through. Stroke: thin dark border at high zoom, none at low zoom.

### Basemaps

Match PEIT Map Creator's basemap options:
- Street (OpenStreetMap)
- Light (CartoDB Positron) — **default**
- Dark (CartoDB Dark Matter)
- Satellite (ESRI World Imagery)

### Hex Tile Interactions

**Hover:** Highlight hex border, show tooltip with friction score and top contributing layers.

**Click / Popup:** Detailed popup showing:
- Friction score with color indicator
- Complete layer breakdown (layer name, category, friction tier)
- For each layer: link to the responsible agency/permitting resource (populated from `prism_layers.permit_start_url`)
- H3 index and geographic coordinates

**Agency links in popups (later phase):** Each layer in the popup should link to the web resource or agency where a user would begin the permitting process. For example, if "USFWS Critical Habitat" is present, link to the IPaC portal. If "FEMA Flood Zone" is present, link to FEMA's flood map service center. This data lives in the `prism_layers` table and is populated during the layer evaluation task.

### Filtering

**Geographic filters** (top bar or side panel):
- State dropdown (multi-select)
- County dropdown (filtered by selected state)
- Congressional District dropdown
- These filters should clip the viewport and filter the tile query to only return hexes within the selected geography

**Score filters:**
- Friction score range slider (0-100)
- Layer category toggles (show/hide hexes affected by specific categories)

**Custom polygon filter:**
- Upload button supporting: Shapefile (ZIP), KML, KMZ, GeoJSON, GeoPackage
- Draw tool (using Leaflet Geoman, matching PEIT Map Creator's implementation)
- Uploaded/drawn polygon: displays on map, filters out non-intersecting hexes, zooms to extent
- Client-side file parsing using the same libraries as PEIT: shpjs, @tmcw/togeojson, jszip, @ngageoint/geopackage

Reuse PEIT Map Creator's `file-parsers.ts`, `validation.ts`, and `geojson-utils.ts` for polygon upload/draw functionality.

### Responsive Design

Mobile-friendly but desktop-optimized. Panels collapse to bottom sheet on mobile. Touch-friendly hex interaction.

---

## HexRoute Integration

PRISM must be designed so its hex layer can be toggled within the HexRoute application as an overlay:

1. **Shared data format:** PRISM tiles served as GeoJSON FeatureCollections with a consistent schema that HexRoute can consume
2. **Layer toggle API:** Expose PRISM as a self-contained Leaflet layer class or React component that HexRoute can import:
   ```tsx
   import { PrismHexLayer } from '@prism/map-layer';
   // or
   import { PrismHexLayer } from '../prism/components/PrismHexLayer';
   ```
3. **Shared H3 utilities:** Common resolution-switching logic, color ramp, and popup formatting
4. **Supabase integration:** Both apps query the same Supabase instance; PRISM tables are namespaced with `prism_` prefix

Consider structuring PRISM as a monorepo package or a shared component library that both the standalone PRISM app and HexRoute can consume.

---

## Paid Analysis Feature (Future Phase)

A premium feature where users upload a polygon/multipolygon and receive algorithmically-generated "environmental project areas" — logical subdivisions of their project footprint based on permitting friction boundaries.

### Concept

Given a user's project boundary polygon:
1. Overlay the PRISM friction grid at R9 resolution
2. Identify clusters of contiguous hexes with similar friction profiles
3. Generate project area boundaries using voronoi tessellation, watershed-style segmentation, or contiguity-based clustering
4. Output: a set of polygons representing recommended NEPA project areas, each with a friction summary and permitting layer breakdown

### Implementation

- **Trigger:** User uploads polygon via the custom polygon filter, then clicks "Generate Environmental Project Areas"
- **Backend:** Modal.com job (Python)
  - Input: GeoJSON polygon + PRISM hex data for the area
  - Processing: Spatial clustering algorithm (evaluate: DBSCAN on friction features, k-means with spatial constraint, region-growing, or voronoi seeded by friction gradient peaks)
  - Output: GeoJSON FeatureCollection of project area polygons with metadata
- **Payment:** Gate behind authentication + usage-based pricing (Stripe integration or credit system)
- **Result delivery:** Real-time progress via SSE (matching PEIT's `processing-status.tsx` pattern), result displayed on map and available for download as GeoJSON/Shapefile

### Rate Limiting

Match PEIT's rate limiting architecture:
- Anonymous: not available (auth required for paid features)
- Authenticated free: 1-2 runs
- Paid: usage-based

---

## Project Structure

```
prism/
├── README.md
├── CLAUDE.md                          # Project context for Claude Code sessions
├── package.json
├── next.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
│
├── app/                               # Next.js App Router
│   ├── layout.tsx                     # Root layout with providers
│   ├── page.tsx                       # Main map page
│   ├── api/
│   │   ├── tiles/route.ts            # Tile serving endpoint
│   │   ├── layers/route.ts           # Layer metadata endpoint
│   │   └── analyze/route.ts          # Proxy to Modal analysis job
│   └── auth/                          # Supabase auth pages
│
├── components/
│   ├── map/
│   │   ├── PrismMap.tsx              # Main map component
│   │   ├── PrismHexLayer.tsx         # H3 hex layer (exportable for HexRoute)
│   │   ├── HexPopup.tsx             # Hex detail popup
│   │   ├── HexTooltip.tsx           # Hover tooltip
│   │   ├── BasemapSwitcher.tsx      # Basemap control
│   │   └── DrawControl.tsx          # Geoman drawing tools
│   ├── filters/
│   │   ├── GeographyFilter.tsx      # State/County/District dropdowns
│   │   ├── ScoreFilter.tsx          # Friction score range slider
│   │   ├── CategoryFilter.tsx       # Layer category toggles
│   │   └── PolygonUpload.tsx        # File upload + draw
│   ├── panels/
│   │   ├── Legend.tsx               # Color ramp legend
│   │   ├── LayerPanel.tsx           # Layer info panel
│   │   └── AnalysisPanel.tsx        # Paid analysis UI
│   └── ui/                           # shadcn/ui components
│
├── lib/
│   ├── supabase/
│   │   ├── client.ts                # Browser Supabase client
│   │   ├── server.ts                # Server Supabase client
│   │   └── types.ts                 # Generated types
│   ├── h3/
│   │   ├── resolution.ts           # Zoom-to-resolution mapping
│   │   ├── colors.ts               # Friction-to-color ramp
│   │   └── utils.ts                # H3 utility functions
│   ├── tiles/
│   │   ├── fetcher.ts              # Tile data fetching with caching
│   │   └── cache.ts                # Client-side LRU tile cache
│   ├── file-parsers.ts              # Geospatial file parsing (from PEIT)
│   ├── validation.ts                # File validation (from PEIT)
│   └── geojson-utils.ts            # GeoJSON utilities (from PEIT)
│
├── modal/                            # Modal.com Python backend
│   ├── modal_app.py                 # Modal app definition
│   ├── requirements.txt
│   ├── ingest/
│   │   ├── layer_ingest.py         # ESRI REST layer ingest
│   │   ├── arcgis_query.py         # Query strategy (from PEIT)
│   │   └── geometry_converters.py  # ESRI JSON <-> GeoJSON (from PEIT)
│   ├── indexing/
│   │   ├── h3_indexer.py           # H3 hex indexing pipeline
│   │   ├── aggregator.py           # R9 -> R8 -> R7 aggregation
│   │   └── score_calculator.py     # Composite friction scoring
│   ├── analysis/
│   │   ├── project_areas.py        # Voronoi/clustering analysis (paid feature)
│   │   └── report_generator.py     # PDF/Excel export
│   └── config/
│       └── layers_config.json      # Layer catalog (from APPEIT scan_aprx)
│
├── supabase/
│   └── migrations/
│       ├── 001_create_hex_tables.sql
│       ├── 002_create_layer_tables.sql
│       ├── 003_create_geography_tables.sql
│       └── 004_create_indexes.sql
│
└── public/
    └── ...                           # Static assets
```

---

## Development Phases

### Phase 1: Data Foundation (Highest Priority)
- [ ] Set up Supabase project with PostGIS
- [ ] Create database schema (hex tables, layer tables, indexes)
- [ ] Port APPEIT layer catalog (`layer_config_from_rest_noraw.json`) into `prism_layers` table
- [ ] Build Modal.com ingest pipeline for top 50 priority layers
- [ ] Build H3 indexing pipeline (R9 base, aggregate to R8/R7)
- [ ] Implement placeholder friction scoring (layer count proxy)
- [ ] Build and test tile serving endpoint
- [ ] Validate: query a viewport bbox, get hex GeoJSON back in <500ms

### Phase 2: Map UI
- [ ] Scaffold Next.js app with Leaflet map
- [ ] Implement PrismHexLayer with resolution switching on zoom
- [ ] Color ramp rendering with friction score styling
- [ ] Hex hover tooltip and click popup
- [ ] Basemap switcher
- [ ] Legend component
- [ ] Dark/light mode

### Phase 3: Filtering & Interaction
- [ ] Geographic filter dropdowns (State/County/District)
- [ ] Score range slider filter
- [ ] Category toggle filters
- [ ] Polygon upload (port from PEIT)
- [ ] Draw tool (port Geoman integration from PEIT)
- [ ] Polygon-based hex filtering and zoom-to

### Phase 4: Layer Evaluation (Parallel Task)
- [ ] Evaluate all environmental/permitting layers for friction weight
- [ ] Assign tier classifications (high/medium/low)
- [ ] Define composite scoring formula
- [ ] Populate `prism_layers` with weights, tiers, agency URLs, permit start URLs
- [ ] Re-run scoring pipeline with real weights
- [ ] Validate scoring results against known permitting-heavy areas

### Phase 5: HexRoute Integration
- [ ] Extract PrismHexLayer as importable component
- [ ] Define shared data format contract
- [ ] Build toggle integration in HexRoute
- [ ] Test cross-app rendering consistency

### Phase 6: Paid Analysis Feature
- [ ] Build Modal.com analysis job (clustering/voronoi)
- [ ] Implement auth-gated UI
- [ ] SSE progress streaming
- [ ] Result visualization on map
- [ ] Download as GeoJSON/Shapefile
- [ ] Payment integration

### Phase 7: Agency Links & Permitting Resources
- [ ] Populate `permit_start_url` for all layers
- [ ] Build rich popup with agency links
- [ ] Categorize links by permit type and jurisdiction

---

## Key Design Decisions & Constraints

1. **H3 R9 as base resolution.** All indexing computes at R9 and aggregates up. This provides ~100m precision which is sufficient for environmental screening without creating an unmanageable number of hexes nationally.

2. **Pre-aggregated tiles, not dynamic computation.** For performance, friction scores are pre-computed and stored, not calculated on-the-fly. Re-computation happens when layer data or weights change.

3. **Viewport-based tile serving.** The client sends its current bbox and zoom level; the server returns only the hexes visible in that viewport at the appropriate resolution. This keeps payload sizes manageable.

4. **Supabase as the single backend.** No separate tile server. PostGIS spatial queries with proper indexing should handle the query load. If performance becomes an issue, pre-generate PMTiles as a fallback.

5. **Code reuse from PEIT Map Creator.** The polygon upload/draw workflow, ESRI REST query logic, and SSE progress streaming patterns are already battle-tested in PEIT. Port don't rewrite.

6. **Friction weights are decoupled from the index.** The H3 indexing records which layers intersect which hexes. The scoring function runs separately, reading weights from `prism_layers` and computing `friction_score` per hex. This lets the evaluation task proceed independently and supports iterative weight refinement without re-ingesting data.

7. **National scope, progressive disclosure.** At national zoom (z4-6), show R7 hexes — broad regional patterns. Zooming in reveals finer detail. State/County filters are not just for display — they also constrain the database query to keep response times fast.

---

## Reference: APPEIT Layer Catalog

The environmental/permitting layers are sourced from the APPEIT project's scan of 561 ArcGIS Pro layers. The processed configuration (`layer_config_from_rest_noraw.json`) contains 208 layers organized into these categories:

| Category | Layer Count | Examples |
|----------|-------------|---------|
| EPA Programs | 20 | Superfund, RCRA, TRI, NPDES, Air Nonattainment |
| Federal/Tribal Land | 17 | NPS, BLM, USFS, BIA Tribal, USACE, DoD |
| Floodplains | 7 | FEMA Flood Hazards, NWI Wetlands, Wild/Scenic Rivers |
| Critical Habitats | 2 | USFWS Critical Habitat (Final + Proposed) |
| Historic Places | 2 | NRHP Points + Polygons |
| Infrastructure | 16 | Pipelines, Power Plants, Transmission Lines, Railroads |
| State Lands | 106 | State forests, parks, wildlife areas (per-state) |
| State-Specific | ~38 | Alaska DNR, NY Adirondack, Kentucky, Colorado, etc. |

All layers are served as ESRI ArcGIS REST FeatureServer endpoints. The ingest pipeline queries these endpoints using the same POST-based strategy as PEIT Map Creator (handles pagination, geometry simplification, timeout fallbacks).

---

## Reference: Technology Codes (FCC BDC)

For BEAD project context, these are the FCC technology codes used in NEPA project area assignment:

| Code | Technology |
|------|-----------|
| 0 | Other |
| 10 | Copper Wire |
| 40 | Coaxial Cable / HFC |
| 50 | Optical Carrier / Fiber to the Premises |
| 61 | Non-Geostationary Satellite |
| 70 | Unlicensed Terrestrial Fixed Wireless |
| 71 | Licensed Terrestrial Fixed Wireless |
| 72 | Licensed by-Rule Terrestrial Fixed Wireless |

---

## Reference: NEPA Project ID Format

For BEAD-specific analysis features:
- **BEAD Grant Project ID:** `CM61-BEAD-[State]-[Project]-[Subproject]` (e.g., `CM61-BEAD-NV-1234-5`)
- **NEPA Project ID (when split):** Append `-N[number]` (e.g., `CM61-BEAD-NV-1234-5-N1`)
