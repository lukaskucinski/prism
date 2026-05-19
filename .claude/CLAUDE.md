# PRISM — Claude Code project guide

A national-scale H3-hex web map of environmental and permitting friction. Each ~460 m² hex is scored by overlapping environmental, historic, and regulatory data layers (USFWS Critical Habitat, FEMA Flood, NWI Wetlands, NRHP, BLM/USFS/NPS, EPA programs, Tribal lands — 131 layers from the APPEIT catalog). Standalone Next.js + Mapbox + Supabase. Pilot scope: **Vermont on Supabase, Nevada via local GeoPackage**.

## Quick start

```powershell
# Frontend (port 3001 — HSNV3 holds 3000)
pnpm install
pnpm dev -p 3001

# Python pipeline (claude conda env; never touch base)
$conda = "C:\Users\lukas\anaconda3\Scripts\conda.exe"
& $conda run -n claude --no-capture-output python -m prism.boundaries.load_tiger
& $conda run -n claude --no-capture-output python -m prism.ingest --states VT
& $conda run -n claude --no-capture-output python -m prism.score --aggregate
```

After scoring, **bump `NEXT_PUBLIC_TILE_VERSION` in `.env`** and restart `pnpm dev` to invalidate tile cache.

## Critical conventions (do not re-litigate these without reason)

- **Mapbox GL JS 3.18, not Leaflet.** Required for HexRoute integration. See [ARCHITECTURE](./docs/ARCHITECTURE.md).
- **H3 base resolution R8, not R9.** Aligns with HexRoute and FCC BDC. Aggregate up to R7 (z 7–9), R6 (z ≤ 6).
- **MVT vector tiles via `prism_get_hex_mvt(z,x,y,filter_json)` RPC.** Not GeoJSON.
- **Per-state AOI loop in ingest, never union'd.** Union'd bbox triggers ArcGIS envelope-mode → wrong-region features → all filtered out.
- **VT only in Supabase** (~95 MB of 500 MB cap). NV / other states use `--local-output <gpkg>` — see [SCOPE_AND_PHASES](./docs/SCOPE_AND_PHASES.md).
- **Local Python pipeline for v1.** Modal.com deferred to Phase 6 (paid feature) — $0 cost in v1, fits the user's Modal free-tier budget.
- **Tile URLs must be absolute** (Mapbox Worker can't parse relative). See `lib/tiles/url.ts`.
- **Memoize `paint` props** on Mapbox layer wrappers. Otherwise the source remounts every render. See `components/map/PrismMap.tsx`.
- **`SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE`** is required on every psycopg connection — Supabase project-level `default_transaction_read_only=on`. Already in `prism.db.pg_conn()`.
- **Conda env is `claude`, not `base`.** Never `pip install` into base (breaks Anaconda Navigator).

## Project map

```
prism/
├── app/                       Next.js 16 App Router (page + API routes)
├── components/{map,filters,panels,ui}/
├── lib/{store,h3,tiles,map,supabase}/
├── modal/prism/               Python pipeline (runs locally, not on Modal in v1)
│   ├── ingest/                ArcGIS query → H3 cells
│   ├── index/                 R8 → R7 → R6 aggregation
│   ├── score/                 friction scoring
│   ├── seed/, boundaries/
│   └── {db,log,categories}.py
├── supabase/migrations/       7 idempotent DDL files
├── packages/                  Phase 5: @prism/map-layer for HexRoute
├── scripts/                   Local utilities (validators, diagnostics)
└── .claude/                   These docs
```

## Detail documentation

| Doc | When to read |
|---|---|
| [ARCHITECTURE](./docs/ARCHITECTURE.md) | Why-decisions (Mapbox vs Leaflet, R8 vs R9, etc.). Read before proposing changes that touch load-bearing choices. |
| [DATA_PIPELINE](./docs/DATA_PIPELINE.md) | Ingest → index → score flow. Per-state AOI loop. ArcGIS quirks. `--local-output` mode. |
| [SUPABASE](./docs/SUPABASE.md) | Project ref + schema. Free-tier survival kit. Long-query gotchas (TCP keepalive, statement_timeout, SSL EOFs). |
| [FRONTEND](./docs/FRONTEND.md) | Three painful Mapbox traps that wasted hours. Component structure. State mgmt. Debugging recipes. |
| [LOCAL_DEV](./docs/LOCAL_DEV.md) | First-time setup. Conda env pattern. Troubleshooting table. |
| [SCOPE_AND_PHASES](./docs/SCOPE_AND_PHASES.md) | What's shipped, what's deferred, known open items (e.g. Electric Retail Service Territories layer over-blankets VT — Phase 4 fix). |
| [DESIGN](./docs/DESIGN.md) | Visual language, friction color ramp, design tokens, component patterns. |
| [SECURITY](./docs/SECURITY.md) | Secrets, RLS, password URL-encoding. Phase 6 readiness for auth + Stripe. |
| [TESTING](./docs/TESTING.md) | No automated tests yet. Manual checklist for "is the pilot working". Priorities for hardening. |

## Working with the user

- Confirm before non-reversible operations (DROP, force-push, etc.).
- Conventional commit messages (`feat:`, `fix:`, `chore:`, `docs:`).
- Push directly to `main` — no PR required pre-Phase-5.
- Long-running pipeline / build commands: use `run_in_background=true` and stream events via Monitor.
- Bumping `NEXT_PUBLIC_TILE_VERSION` is part of any change that affects tile content.

## Key external endpoints

- Supabase project: `https://uuqxqqcelabpacljeqgm.supabase.co` (ITG org)
- HexRoute project (same org, sibling): `llfnysraszaaolcxwsaj`
- Mapbox dashboard token URL allowlist: `localhost:3000/`, `localhost:3001/`
- Production target: `prism.kucimaps.com` (DNS not yet configured)
- Repo: `https://github.com/lukaskucinski/prism.git`

## Notes and learnings

- The aggregator (`prism.index.aggregator`) is slow (~11 min for VT's 57 k hexes) because it does per-parent INSERTs. Bulk INSERT-SELECT would be much faster — optimization candidate before any NV-scale work.
- ArcGIS catalog has internal duplicates: 208 raw entries → 131 unique by (name, service, layer_id). See `scripts/check-duplicates.mjs`.
- TIGER 2024 Congressional Districts ship only as per-state zips, never US-combined — `prism.boundaries.load_tiger` handles this.
- When the Supabase MCP returns "permission denied" on a project, it's because the auth token is scoped to a different org. The user can re-authenticate via Supabase settings to switch the MCP's accessible org.
- NumPy 2 + Shapely 2.0.x → import error. Upgrade Shapely to 2.1+ (already done in the `claude` env).
