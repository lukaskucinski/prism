# Scope & Phases

What's actually shipped right now and what remains.

## Current scope (May 2026)

| Dimension | Status |
|---|---|
| Live web map | Vermont only, via Supabase tiles |
| Local analytical | Any state via `--local-output <gpkg>` (designed for Nevada) |
| Layer catalog | 131 layers from APPEIT (deduplicated from 208) |
| Friction weights | Placeholder tiered (high=30, medium=15, low=5 by category) |
| Auth | None — fully public map (matches HexRoute pattern in v1) |
| Cost | $0 — free-tier Supabase + Mapbox public token |

## Phases status

### ✅ Phase 0 — Repo bootstrap
- Git initialized, pushed to `https://github.com/lukaskucinski/prism.git`
- `.gitignore`, README.md, RUNBOOK.md
- Not auto-deployed to Vercel yet

### ✅ Phase 1 — Data foundation
- Supabase project + 7 migrations applied
- 131 layers seeded into `prism_layers`
- TIGER 2024 boundaries loaded for VT (states/counties/CDs)
- Python pipeline (lifted PEIT's ArcGIS query + geometry converters, added LocalSink for NV)
- Full VT ingest complete: 36 ok / 4 fail / 91 skip
- R8 = 57,658 hexes scored; R7 = 8,848; R6 = 1,381
- MVT RPC working and returning real tiles at z=5/8/10

### ✅ Phase 2 — Map UI shell
- Mapbox map renders dark basemap centered on VT
- Hex layer with magma-family color ramp
- Hover tooltip + click popup with layer breakdown
- Basemap switcher (dark/light/streets/satellite)
- Filter panel + Layer admin panel UI exists
- Geography / score / category API routes exist
- URL hash sync for shareable links

### 🚧 Phase 3 — Filtering & polygon upload
Code paths exist; needs validation:
- Filter wiring through `filterHash` → tile URL — written but unverified end-to-end with non-empty filters
- Polygon upload UI not yet built (`lib/file-parsers.ts` lifted from PEIT but not wired to a component)
- Polygon-draw via Mapbox GL Draw not started

### ⏳ Phase 4 — Layer evaluation (parallel task)
Outside engineering scope; subject-matter expert work. Needs to:
- Set real `friction_weight` per layer in `prism_layers`
- Set `agency_name`, `agency_url`, `permit_start_url`
- Validate friction signal against known permitting hotspots

### ⏳ Phase 5 — HexRoute integration
Extract `components/map/HexLayer.tsx` (or a Vanilla-JS variant) into `packages/prism-map-layer/` and publish as `@prism/map-layer` to GitHub Packages. HexRoute installs it and adds a layer toggle.

### ⏳ Phase 6 — Paid analysis feature
- Supabase Auth + RLS policies on `user_id`-attributed tables
- Stripe (or credit) integration
- Modal.com worker for spatial-clustering / voronoi project-area generation
- SSE progress streaming (port PEIT's pattern)

### ⏳ Phase 7 — Agency links in popups
Depends on Phase 4 — once `permit_start_url` is populated, the popup renders link buttons per intersecting layer.

## Known open items / debt

### Electric Retail Service Territories blankets the entire state
This HIFLD layer has 21 overlapping utility-territory polygons that cover all of VT. After H3 indexing it claims **55,148 hexes — every hex in our ingest is "in" this layer.** Currently `friction_weight=5` (low tier), so it just raises the baseline of every hex by 5 points.

It's not a permitting-friction layer in any real sense — being in a utility's service area doesn't add NEPA burden. Phase 4 layer-evaluation should set its weight to 0. Until then, expect every VT hex to read at least "Minimal" friction (instead of zero / no-data).

### 4 layers failed during VT ingest
Inspect with: `SELECT layer_name, last_ingest_error FROM prism_layers WHERE ingest_status='failed';`

Known patterns:
- **CBRS Units** (`cbrsgis.wim.usgs.gov`) — connection timeout; service was down at ingest time. Harmless for VT (CBRS is coastal).
- **2 layers** failed with `HTTP 405 Method Not Allowed` — PEIT's query strategy only does POST; some MapServer endpoints (Massachusetts in particular) require GET. To recover, add a GET fallback to `arcgis_query.py`.

### Pagination cap caught one layer
USFWS Wetlands hit the 50-page × 2000-feature pagination cap in VT (more wetlands than expected). The portion ingested is real; some hexes that should have wetlands flagged don't. For PRISM's pilot use case this is acceptable — Phase 4 layer-evaluation can decide whether to do per-county ingests for affected layers.

### Layer-evaluation task not started
Until Phase 4 lands, every layer carries placeholder tier weights. Map will render meaningfully (color gradient is real) but the precise scores are not calibrated.

### Aggregator is slow
`prism.index.aggregator` does per-parent INSERT/UPDATE via `psycopg.executemany`. R7 took ~11 min for VT, R6 ~2 min. A bulk `INSERT ... SELECT ... GROUP BY` would be much faster — optimization candidate before NV-scale runs.

### CI/CD not wired
- Vercel auto-deploy is configured at the dashboard level (the repo is connected) but no production deployment has happened yet.
- No GitHub Actions for migration verification, lint, or Python tests.
- `prism.kucimaps.com` DNS not yet configured.

### No Sentry / observability
`@sentry/nextjs` is in `package.json` but not wired into `app/layout.tsx` or any API route. Phase 1H done in code only.

### No test suite
See [TESTING](./TESTING.md).

## Pilot validation criteria (for declaring Phase 1+2 done)

- ✅ Tile RPC returns < 200 ms at z=8 over VT
- ✅ Map renders colored hexes over VT in browser
- ✅ Hover tooltip + click popup work
- ✅ DB stays under 500 MB free-tier cap (currently 95 MB)
- ⏳ Friction colors visually correlate with known permitting hotspots (blocked on Phase 4)
- ⏳ Cross-platform tested (only verified on Chrome / Edge / Win11 so far)
