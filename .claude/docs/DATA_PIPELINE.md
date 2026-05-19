# Data Pipeline

Ingest → H3 index → score → MVT. End-to-end Python pipeline running locally in the `claude` conda env. Source code in `modal/prism/`.

## Pipeline stages

```
prism.boundaries.load_tiger      (one-time, ~30s per state)
       ↓
prism.seed.load_layers            (one-time, < 1s)
       ↓
prism.ingest --states VT          (per-layer × per-state, ~16 min for VT/131 layers)
       ↓
prism.score --aggregate           (R8 rescore + R7/R6 rebuild, ~12 min)
       ↓
prism.index                       (R7/R6 only, if R8 unchanged)
```

Every stage updates `prism_ingest_log` for an auditable trail. Per-layer status (`success | partial | failed | skipped | pending`) is also written to `prism_layers.ingest_status`.

## Per-state AOI loop — non-negotiable

**Iterate states one at a time, do NOT union them.** Union'd AOI (e.g. VT+NV) has a giant bounding box covering most of the western US; ArcGIS often falls back to envelope-mode queries against that bbox, returns ~2000 California/Arizona features, and the client-side polygon-intersection filter rejects all of them. Net: zero hexes from layers that have real data in your AOI.

Implementation: `prism.ingest.layer_ingest.fetch_state_aois()` returns a dict `{state_abbr → BaseGeometry}`. CLI loops over states inside the layer loop. Each (layer × state) is its own arcgis query.

## ArcGIS query strategy (lifted from PEIT)

Two modes, chosen automatically per query:

1. **Polygon mode** (preferred): sends pre-computed ESRI JSON polygon as the spatial filter via POST. Most precise, fewest false positives.
2. **Envelope mode** (fallback): sends just the bbox. Used when polygon mode fails server-side.

**For polygon mode to work, you must pre-compute the ESRI JSON.** `_build_polygon_query_payload(aoi)` in `layer_ingest.py` does this:
- Counts vertices; if >1000, applies `simplify_for_query()` with progressive tolerance
- Calls `shapely_to_esri_polygon()` to produce the ESRI JSON dict
- Passes `esri_polygon_json` + metadata to `query_arcgis_layer()`

If you skip this, every layer goes to envelope mode and most return junk.

## Pagination cap

Bumped from PEIT's default 10 pages to **50 pages × 2000 features = 100k per layer × state**. Some layers (USFWS Wetlands, dense point services) exceed this. The `query_arcgis_layer` logs a warning when the cap is hit; the per-state portion is still useful but incomplete.

If you need full coverage of a specific layer, run a targeted ingest with smaller AOIs (e.g. one county at a time).

## Layer failure modes seen in practice

These are tolerated by the lenient + retry-with-backoff pipeline (`tenacity`, 3 attempts × exponential up to 30s):

- **`HTTPSConnectionPool ... ConnectTimeoutError`** — service unreachable (e.g. `cbrsgis.wim.usgs.gov`). Layer marked `failed`.
- **`HTTP 405 Method Not Allowed`** — endpoint rejects POST. PEIT's strategy only does POST. Add GET fallback later if these layers matter; for now they're marked `failed`. (Seen on some Massachusetts and other state services.)
- **`HTTP 5xx`** — server-side. Retried with backoff.
- **Empty result + `assigning CRS to GeoDataFrame without geometry column`** — GeoPandas 1.x rejects `from_features([], crs=...)`. Fixed in `arcgis_query.py` with explicit empty-GDF construction.

Inspect failures: `SELECT layer_name, last_ingest_error FROM prism_layers WHERE ingest_status='failed';`

## H3 indexing

`prism/index/h3_indexer.py::features_to_r8_cells(gdf, geometry_type, friction_category)`:

| Geometry | How |
|---|---|
| polygon / MultiPolygon | `h3.polygon_to_cells(LatLngPoly, res=8)` per ring, holes preserved |
| line / MultiLineString | Buffer (Web Mercator → meters → WGS84 round-trip), then polygon-to-cells. Default 152 m; category-tuned for `infrastructure` (152 m), `floodplain_wetland` (100 m), `historic` (50 m) |
| point / MultiPoint | `h3.latlng_to_cell(lat, lng, 8)` |

Returns `[(h3_index, feature_count)]` deduplicated within the layer.

## Hex polygon writing

`_write_hexes(layer_id, cell_counts)` does two upserts per layer:
1. `INSERT INTO prism_hex_r8 (h3_index, geom) ... ON CONFLICT DO NOTHING` — writes the hex polygon (computed via `cell_polygon_wkt(h3_index)` in Python)
2. `INSERT INTO prism_hex_layer (h3_index, layer_id, feature_count) ... ON CONFLICT (h3_index, layer_id) DO UPDATE SET feature_count = EXCLUDED.feature_count`

Hex polygons are only computed in Python (Supabase has no `h3` extension). If you later need the polygon for a hex not in the table, recompute via `cell_polygon_wkt`.

## Scoring

`prism.score.scorer.rescore_r8()` runs in chunks of 50k h3 indexes:

1. Create UNLOGGED table `prism_hex_score_tmp(h3_index, friction_score, layer_count, top_friction_driver, category_flags)`
2. For each 50k batch of distinct h3 indexes from `prism_hex_layer`:
   - Aggregate via `GROUP BY hl.h3_index` joining `prism_hex_layer × prism_layers`
   - `friction_score = min(100, sum(friction_weight))`
   - `layer_count = count(distinct layer_id)`
   - `top_friction_driver = (array_agg(layer_name ORDER BY friction_weight DESC))[1]` — no correlated subquery
   - `category_flags = jsonb_object_agg(friction_category, true)`
3. Single `UPDATE prism_hex_r8 r FROM prism_hex_score_tmp s WHERE r.h3_index=s.h3_index`
4. DROP the temp table

Why chunked: a single GROUP BY over the full join table holds the Supabase connection open too long for the pooler. SSL EOFs result. 50k chunks complete in seconds and keep the connection responsive. See [SUPABASE](./SUPABASE.md) for full background.

Aggregator (`prism.index.aggregator`) then rebuilds `prism_hex_r7` and `prism_hex_r6` by `h3.cell_to_parent` rollup of children. Slow (~11 min for VT) because it does per-parent INSERTs via psycopg `executemany` — optimization candidate.

## Local-output mode (NV / non-Supabase scope)

`prism.ingest --states NV --local-output data/nv-hexes.gpkg` writes hex+join rows to a GeoPackage instead of Supabase. Why: NV ingest blows past the 500 MB free-tier cap (federal lands cover ~85% of NV, each polygon fills 100k+ hexes).

GPKG schema:
- Layer `prism_hexes_r8`: (h3_index TEXT, geom Polygon)
- Layer `prism_hex_layer`: (h3_index, layer_id, layer_name, friction_category, feature_count) — non-geometric, written via `pyogrio.write_dataframe`

Layer-level metadata (`prism_layers.ingest_status`, `prism_ingest_log`) still goes to Supabase — single audit trail across both modes.

Implementation: `LocalSink` class in `prism/ingest/local_sink.py`. Buffers writes and flushes every 25k rows.

## Re-running individual steps

| Goal | Command |
|---|---|
| Retry only failed layers | `python -m prism.ingest --only-failed` |
| Re-ingest one specific layer | `python -m prism.ingest --layers nps_land__NPS_Land_Permitting_Layer-0` |
| Re-score after weight changes | `python -m prism.score --aggregate` |
| Re-aggregate only (R8 unchanged) | `python -m prism.index` |
| Wipe + start over | `python scripts/cleanup-for-vt-only.py` |

After any rescore, bump `NEXT_PUBLIC_TILE_VERSION` in `.env` to invalidate CDN tile cache.
