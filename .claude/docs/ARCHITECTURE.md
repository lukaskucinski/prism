# Architecture

Why the system is built the way it is. Decisions made up-front and the reasons behind them — useful when proposing changes that touch these load-bearing choices.

## Stack at a glance

| Layer | Choice |
|---|---|
| Map renderer | **Mapbox GL JS 3.18+** |
| Hex grid | **H3, base resolution 8** (aggregated up to R7, R6) |
| Tiles | **MVT vector tiles** served by a PostGIS RPC |
| Database | **Supabase Postgres 17 + PostGIS 3.3.7** (free tier, 500 MB) |
| Backend | Next.js 16 App Router API routes (Node runtime) |
| Frontend | React 19 + TypeScript strict + Tailwind v4 + Zustand |
| Compute | **Local Python (`claude` conda env)** in v1; Modal.com deferred to Phase 6 |
| Hosting target | Vercel + Cloudflare in front; deploy at `prism.kucimaps.com` |

## Headline decisions (and the alternatives that lost)

### Mapbox GL JS, not Leaflet
The original prompt said Leaflet. We switched because HexRoute (the parent app PRISM will integrate into) is on Mapbox GL JS 3.18, and a Leaflet PRISM cannot be embedded as a layer in a Mapbox map. Switching also gave us GPU-accelerated vector-tile rendering at high hex counts.

Downstream: drawing tools become Mapbox GL Draw (not Geoman); polygon-upload parsing libs (shpjs, togeojson, jszip, ngageoint/geopackage) still port directly from PEIT.

### H3 R8 base resolution, not R9
Original prompt said R9 (~100m hex edge). We chose R8 (~460m edge) so PRISM hexes line up exactly with HexRoute (which uses FCC BDC's canonical R8). R9 would produce 4× more hexes nationally and visually mis-align when toggling between apps. Permitting screening doesn't need sub-parcel precision.

Aggregation: R8 → R7 → R6 via `h3.cell_to_parent`. Zoom-to-resolution map:
- z ≤ 6 → R6 (~36 km², regional overview)
- z 7–9 → R7 (~5 km², state/region detail)
- z ≥ 10 → R8 (base, county/site detail)

### MVT vector tiles, not GeoJSON FeatureCollections
~10× smaller payloads. Mapbox renders MVT natively without parse cost. Server-side resolution switching in the RPC (`prism_get_hex_mvt(z,x,y,filter_json)`) means one endpoint, three zoom branches. Pattern lifted from HexRoute's `get_hex_mvt` RPC.

### Sparse hex storage
Only hexes intersecting ≥1 layer get a row in `prism_hex_r8`. Empty regions show basemap through. Saves 4× on storage vs. dense (every R8 cell in the AOI). The CONUS-density estimate that bit us was: dense storage at R8 = ~12M rows; sparse = ~3M rows. We still hit free-tier limits at full coverage (see [SCOPE_AND_PHASES](./SCOPE_AND_PHASES.md)) — sparse just buys headroom.

### Hybrid hex-layer storage
Two tables instead of one denormalized row:
- `prism_hex_layer (h3_index, layer_id, feature_count)` — source of truth, easy to incrementally update one layer's contribution
- `prism_hex_r8` — denormalized read columns (`friction_score`, `layer_count`, `top_friction_driver`, `category_flags`) populated by the scorer, optimized for tile reads

Tile RPC reads only the hex tables. Hex-click popup joins through `prism_hex_layer × prism_layers` for the per-layer breakdown.

### Separate Supabase project, not shared with HexRoute
HexRoute and PRISM both live in the **ITG** Supabase org but have separate project refs (`llfnysraszaaolcxwsaj` and `uuqxqqcelabpacljeqgm` respectively). PRISM tables are all prefixed `prism_*` anyway, but having a separate project means:
- Independent storage quotas
- Independent rollback / restore
- No cross-project leakage of credentials or RLS

Cost: cross-app data joins require API calls, not SQL. That's fine — PRISM is a self-contained tile producer; HexRoute consumes its tiles, not its tables.

### Friction model
Each layer carries a numeric `friction_weight` and tier label (`high`/`medium`/`low`) in `prism_layers`. The placeholder v1 weights are **tiered by category**:

| Tier | Weight | Categories |
|---|---|---|
| high | 30 | critical_habitat, floodplain_wetland |
| medium | 15 | historic, tribal_federal_land, epa_program, environmental_justice |
| low | 5 | state_protected, infrastructure |

Per-hex score: `min(100, sum(weight of intersecting layers))`. Categories collapse 18 APPEIT raw groups into 8 frictions categories (`prism/categories.py` ↔ `lib/h3/categories.ts` — keep these in sync).

The layer-evaluation task (Phase 4) replaces this with empirically-validated per-layer weights and tier classifications.

### Color ramp: magma family
User chose Viridis-family in the design grilling; we implemented `inferno`/`magma`-style stops in `lib/h3/colors.ts` (deep purple → bright yellow). High friction reads as warm/bright, low as dark, which fits the "fire = bad" mental model better than literal Viridis (which maps low to dark purple and high to yellow-green).

### Compute hosting: local Python for v1, Modal for paid feature only
The `modal/` directory holds Python code but is run **locally** via `conda run -n claude python -m prism.*` for v1. Modal deployment is deferred to Phase 6 (paid analysis feature) where serverless on-demand compute earns its keep per paying user.

Reasoning: 131-layer VT ingest takes ~16 minutes on a beefy desktop, and the user is on Modal's free tier ($5/mo budget). Local zero-cost execution preserves Modal budget for the actual paid use case.

### Pilot scope: VT only on Supabase
Original plan was VT + NV both on Supabase. Hit Supabase free-tier 500 MB cap at 858 MB (NV has too much federal land — every BLM/USFS polygon h3-fills 100k+ hexes). Pivoted to **VT on Supabase + NV / other states via `--local-output <gpkg>`** which writes the same schema to a local GeoPackage instead. See [SCOPE_AND_PHASES](./SCOPE_AND_PHASES.md) for what's currently in scope.

## Repo layout

```
prism/
├── app/                       # Next.js 16 App Router
│   ├── api/{tiles,hex,layers,states,counties,districts}/
│   ├── page.tsx               # Single-page map
│   └── layout.tsx, globals.css
├── components/{map,filters,panels,ui}/
├── lib/{store,h3,tiles,map,supabase,utils,file-parsers}/
├── modal/                     # Python pipeline (runs locally in v1)
│   └── prism/
│       ├── ingest/            # ArcGIS query → H3 cells
│       ├── index/             # R8 → R7 → R6 aggregation
│       ├── score/             # friction scoring
│       ├── seed/              # one-time prism_layers seed
│       ├── boundaries/        # TIGER 2024 loader
│       └── {db,log,categories}.py
├── supabase/
│   ├── migrations/            # 001-007 idempotent DDL
│   └── seed/prism_layers.sql  # 131 layers
├── packages/                  # Phase 5: @prism/map-layer for HexRoute
├── scripts/                   # Local utilities (validators, diagnostics)
└── .claude/                   # This documentation
```

See [LOCAL_DEV](./LOCAL_DEV.md) for setup, [DATA_PIPELINE](./DATA_PIPELINE.md) for ingest flow, [SUPABASE](./SUPABASE.md) for DB.
