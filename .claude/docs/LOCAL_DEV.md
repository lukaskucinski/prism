# Local Development

Windows + PowerShell + conda + pnpm.

## Prerequisites

- **Node 22+, pnpm 10+** (frontend)
- **Anaconda** with the `claude` env (Python pipeline). Located at `C:\Users\lukas\anaconda3\`.
- **Mapbox public token** (already configured in `.env`)
- **Supabase service-role key** + DB password (already in `.env`)

## First-time setup

```powershell
# 1. Clone, install Node deps
git clone https://github.com/lukaskucinski/prism.git
cd prism
pnpm install

# 2. Install the Python package into the claude conda env (editable)
& "C:\Users\lukas\anaconda3\Scripts\conda.exe" run -n claude pip install -e .\modal

# 3. Create .env in repo root with the variables listed below (template
#    not committed; copy from a previous machine or 1Password).
#    See SUPABASE.md for password URL-encoding caveats.

# 4. Validate the .env DB URL (does not echo password)
node scripts/check-db-url.mjs

# 5. Probe DB connection (does not echo password; runs a write probe)
& "C:\Users\lukas\anaconda3\Scripts\conda.exe" run -n claude python scripts/diagnose-db-conn.py
```

If steps 4 or 5 fail, fix the env before continuing.

## Conda env activation pattern

Bash within Claude Code can't `conda activate` the env (the harness's bash is a fresh shell each time). **Always use `conda run -n claude --no-capture-output`** for Python commands so they execute inside the env without needing activation:

```powershell
& "C:\Users\lukas\anaconda3\Scripts\conda.exe" run -n claude --no-capture-output python -m prism.ingest --states VT
```

The `--no-capture-output` flag streams logs in real time instead of buffering until process exit (essential for long-running pipeline jobs).

**Never install packages into the `base` conda env.** That breaks Anaconda Navigator. The user has multiple envs (`base`, `claude`, `notebooks`, `chanterelle`, `myenv`). PRISM Python deps live in `claude`. Geospatial Jupyter work lives in `notebooks`.

## Running the stack

### Dev server (Next.js frontend + API routes)

```powershell
pnpm dev -p 3001
```

Port 3001 — port 3000 belongs to the HSNV3 portal on this machine. Mapbox token allowlist includes both `:3000/` and `:3001/`.

### Pipeline (one-time or after data changes)

```powershell
$conda = "C:\Users\lukas\anaconda3\Scripts\conda.exe"
& $conda run -n claude python -m prism.boundaries.load_tiger        # TIGER 2024 boundaries (VT)
& $conda run -n claude python -m prism.seed.load_layers              # 131 layers from APPEIT
& $conda run -n claude python -m prism.ingest --states VT            # ~16 min
& $conda run -n claude python -m prism.score --aggregate             # ~12 min
```

After scoring, bump `NEXT_PUBLIC_TILE_VERSION` in `.env` and restart `pnpm dev` to invalidate CDN/client tile cache.

### Local-only analytical ingest (NV or other large states)

```powershell
& $conda run -n claude python -m prism.boundaries.load_tiger --states NV
& $conda run -n claude python -m prism.ingest --states NV --local-output data/nv-hexes.gpkg
```

The GeoPackage is gitignored by default. Read it back with any standard tool: GeoPandas, DuckDB-spatial, QGIS.

## Helpful scripts in `scripts/`

| Script | Purpose |
|---|---|
| `check-db-url.mjs` | Validate `SUPABASE_DB_URL` format without echoing password. Run after editing `.env`. |
| `diagnose-db-conn.py` | Open psycopg connection; show transaction-mode flags + write probe |
| `cleanup-for-vt-only.py` | TRUNCATE hex tables + VACUUM FULL. Use when DB hits free-tier cap. |
| `build-seed-sql.mjs` | Regenerate `supabase/seed/prism_layers.sql` from `modal/prism/config/layers_config.json` |
| `check-duplicates.mjs` | Report duplicate entries in APPEIT layer catalog |
| `smoke-imports.py` | Verify all `prism.*` modules import + Supabase reachable |

## Environment variables

Lives in `.env` (gitignored — never committed). No template is tracked in the repo; the table below is the source of truth.

| Var | Purpose | Required? |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Public Supabase URL | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key for client-side reads | yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side admin key — bypasses RLS | yes |
| `SUPABASE_DB_URL` | Direct psycopg connection string. **Password must be URL-encoded** | yes (Python pipeline) |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Public Mapbox token (`pk.*`) | yes |
| `NEXT_PUBLIC_TILE_VERSION` | Bumped after rescore to bust CDN cache | yes |
| `PRISM_PILOT_STATES` | Default state list for the pipeline (currently `VT`) | yes |
| `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_AUTH_TOKEN` | Sentry. Not yet wired — empty in dev. | no |

`NEXT_PUBLIC_*` are baked into the client bundle at build/start. Restart `pnpm dev` after editing them.

## Troubleshooting common errors

| Error | Cause | Fix |
|---|---|---|
| `Failed to parse URL from /api/tiles/...` | Mapbox worker can't read relative URL | Already fixed — see `lib/tiles/url.ts`. If recurs, ensure `tileUrlTemplate` returns absolute. |
| `containerSize: '1195×0'` in console | Mapbox CSS overrode container position | Already fixed — see `components/map/PrismMap.tsx`. Container needs `h-full w-full`. |
| `numpy.core.multiarray failed to import` (Python) | Shapely 2.0.x compiled against NumPy 1.x; NumPy 2.x is now installed | `pip install --upgrade shapely geopandas fiona pyproj` |
| `cannot execute INSERT/UPDATE/TRUNCATE in a read-only transaction` (Postgres) | Supabase auto-flipped to read-only (disk full) | See [SUPABASE](./SUPABASE.md) recovery section |
| `SSL error: unexpected eof while reading` (psycopg) | Long query killed by Supabase pooler | TCP keepalive in `pg_conn()` + chunk queries to <30s |
| `cannot execute DROP TABLE in a read-only transaction` | Same as above; even MCP can't override | Run via psycopg with `SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE` |
| `404 Not Found` from TIGER zip | 2024 CDs ship per-state, not US-combined | `load_tiger.py` already handles this — file path includes state FIPS |
| `405 Method Not Allowed` from ArcGIS | Some MapServer endpoints don't accept POST | Layer marked `failed`; documented as a known limitation |

## Git workflow

- Trunk-based on `main`. Push directly for now (no PRs required pre-Phase-5).
- Commit messages follow conventional format: `feat:`, `fix:`, `chore:`, `docs:`.
- Remote: `https://github.com/lukaskucinski/prism.git` (private).
