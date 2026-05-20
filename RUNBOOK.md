# PRISM Runbook

End-to-end instructions for setting up local dev, seeding the data pipeline,
and viewing the map for the VT + NV pilot.

## Prerequisites

- **Node.js 22+** and **pnpm 10+** (frontend)
- **Conda** with the `claude` environment activated (Python pipeline)
- **Mapbox account** for a public token (free tier OK)
- **Supabase access** to the PRISM project (`uuqxqqcelabpacljeqgm`)

## 1 — Local env setup

Create `.env` in the repo root. Required variables (full table with purpose +
required flag in [.claude/docs/LOCAL_DEV.md](./.claude/docs/LOCAL_DEV.md#environment-variables)):

```
NEXT_PUBLIC_SUPABASE_URL=https://uuqxqqcelabpacljeqgm.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...    # dashboard → Project Settings → API → anon public
SUPABASE_SERVICE_ROLE_KEY=...        # dashboard → Project Settings → API → service_role secret
SUPABASE_DB_URL=postgresql://postgres:[URL-ENCODED-password]@db.uuqxqqcelabpacljeqgm.supabase.co:5432/postgres
NEXT_PUBLIC_MAPBOX_TOKEN=pk....      # https://account.mapbox.com/access-tokens/
NEXT_PUBLIC_TILE_VERSION=1
PRISM_PILOT_STATES=VT
```

After editing, validate the DB URL (won't echo the password):

```powershell
node scripts/check-db-url.mjs
```

## 1a — Apply migrations + seed (one-time)

```powershell
# Option A: Supabase CLI
supabase link --project-ref uuqxqqcelabpacljeqgm
supabase db push

# Then load the layer catalog seed
psql "$env:SUPABASE_DB_URL" -f supabase/seed/prism_layers.sql

# Option B: paste each file under supabase/migrations/*.sql into the Studio
# SQL editor at https://supabase.com/dashboard/project/uuqxqqcelabpacljeqgm/sql,
# then paste supabase/seed/prism_layers.sql.
```

## 2 — Install dependencies

```powershell
# Frontend
pnpm install

# Python pipeline (in conda 'claude' env)
conda activate claude
pip install -e modal
```

## 3 — Seed the data pipeline

Run these once, in this order. Each takes a few seconds to minutes.

```powershell
# (a) Load TIGER 2024 boundaries (defaults to PRISM_PILOT_STATES=VT)
python -m prism.boundaries.load_tiger

# (b) Seed prism_layers from APPEIT catalog (~131 entries after dedup)
python -m prism.seed.load_layers

# (c) Ingest the full layer catalog into Supabase, clipped to VT
python -m prism.ingest --states VT

# (d) Score + aggregate R8 → R7 → R6
python -m prism.score --aggregate
```

Inspect progress and per-layer results in the `prism_ingest_log` table or in
`prism_layers.ingest_status`.

### Analytical ingests (other states) — local GeoPackage only

Running the full catalog over a large state (e.g. Nevada) generates enough
hex polygons + indexes to overflow the Supabase free-tier 500 MB quota. Use
`--local-output` to write to a GeoPackage on disk instead:

```powershell
python -m prism.boundaries.load_tiger --states VT,NV   # cache NV boundaries
python -m prism.ingest --states NV --local-output data/nv-hexes.gpkg
```

The GPKG contains two layers (`prism_hexes_r8`, `prism_hex_layer`) with the
same column shape as the Supabase tables — read back with GeoPandas /
DuckDB-spatial / QGIS. Layer-level metadata (`prism_layers.ingest_status`,
`prism_ingest_log`) is still updated in Supabase so you keep one audit trail.

## 4 — Run the dev server

```powershell
pnpm dev
```

Open http://localhost:3000. The map should render with a dark Mapbox basemap;
hex polygons appear over VT and NV at zoom 6+.

## 5 — Re-running individual steps

| Goal | Command |
|---|---|
| Re-attempt only failed layers | `python -m prism.ingest --only-failed` |
| Re-ingest one layer | `python -m prism.ingest --layers nps_land__NPS_Land_Permitting_Layer-0` |
| Refresh scores after weight changes | `python -m prism.score --aggregate` |
| Refresh aggregates only | `python -m prism.index` |
| Local-only NV ingest | `python -m prism.ingest --states NV --local-output data/nv-hexes.gpkg` |
| Wipe Supabase hex tables + start over | `python scripts/cleanup-for-vt-only.py` |
| Bust CDN tile cache | Bump `NEXT_PUBLIC_TILE_VERSION` in `.env` and redeploy |

## 6 — Schema

See `supabase/migrations/` for the canonical schema. Tables:

- `prism_layers` — catalog (205 rows after seed)
- `prism_hex_r8`, `prism_hex_r7`, `prism_hex_r6` — sparse hex tables
- `prism_hex_layer` — (h3_index, layer_id, feature_count) join
- `prism_states`, `prism_counties`, `prism_districts` — TIGER 2024 boundaries
- `prism_ingest_log` — append-only pipeline event log

RPC: `prism_get_hex_mvt(z, x, y, filter_json)` — returns MVT tile bytes.

## 7 — Troubleshooting

**"Mapbox token required" overlay** — `NEXT_PUBLIC_MAPBOX_TOKEN` is unset.
Add it to `.env.local` and restart `pnpm dev`.

**Empty map (no hexes visible)** — The data pipeline hasn't run yet, or
state filter is excluding VT/NV. Verify with:
```sql
SELECT count(*) FROM prism_hex_r8;
SELECT ingest_status, count(*) FROM prism_layers GROUP BY 1;
```

**Tile RPC errors in browser console** — Check `SUPABASE_SERVICE_ROLE_KEY` is
set in `.env.local`. Server-side API routes use the admin client.

**Python `ModuleNotFoundError: prism`** — Run `pip install -e modal` again
inside the `claude` conda env.
