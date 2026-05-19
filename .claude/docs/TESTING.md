# Testing

No formal automated test suite yet. Validation is currently scripted (one-off Python / Node smoke scripts) and manual (browser smoke + DB queries via MCP). This will need to harden before production.

## Current verification surface

| Layer | How we verify today |
|---|---|
| `.env` is well-formed | `node scripts/check-db-url.mjs` |
| DB connection works | `python scripts/diagnose-db-conn.py` |
| Python imports succeed | `python scripts/smoke-imports.py` |
| Schema is current | MCP `list_tables` + `list_migrations` |
| Pipeline ran successfully | Inspect `prism_layers.ingest_status` + `prism_ingest_log` |
| Tile RPC works | `curl http://localhost:3001/api/tiles/v2/10/305/372.mvt -o /tmp/t.mvt` (expect > 1 KB binary) |
| Hex popup endpoint | `curl http://localhost:3001/api/hex/{h3_index}` (returns JSON with `layers[]`) |
| Map renders | Open `http://localhost:3001` in Chrome/Edge, look for hexes over VT, hover/click |
| Next.js builds | `pnpm build` (Turbopack) |
| TypeScript clean | `pnpm typecheck` |
| Lint | `pnpm lint` (eslint-config-next + typescript-eslint) |

## What does NOT have a test yet

- The pipeline modules (`prism.ingest`, `prism.index`, `prism.score`). No unit tests, no integration tests.
- API routes. We verify by curl + manual browser; no `vitest` or `playwright` setup.
- The MVT RPC. We verify by curl + visual rendering.
- The `filterHash` round-trip through the URL → tile RPC → SQL filter chain. Not validated end-to-end with non-empty filters.
- Cross-browser. Only Chrome / Edge verified on Win11. Firefox / Safari untested.
- Mobile. Layout will likely break; not yet tested.

## What's worth adding before declaring v1 "done"

### High value, low effort

1. **Pipeline smoke test in Python.**

   `tests/test_pipeline_smoke.py`:
   - Mock a small ArcGIS response
   - Run `ingest_layer` against it
   - Assert hex rows + join rows land in a sqlite/PostGIS test DB
   - Run scorer; assert `friction_score` matches the expected formula
   
   Use `pytest` (already in `dev` extras of `modal/pyproject.toml`).

2. **Next.js API route smoke tests.**
   
   `tests/api/*.test.ts` via `vitest`:
   - `/api/states` returns the expected shape
   - `/api/hex/{invalid}` returns 400, `{valid-but-missing}` returns 404
   - `/api/tiles/v1/8/76/93.mvt` returns 200 + non-empty body when DB has data
   
   Hits the live dev DB (acceptable for v1 — 95 MB doesn't have customer-sensitive data). Pro-tier later can use Supabase branches.

3. **Type-check on every commit.** A simple `pre-commit` hook running `pnpm typecheck`. Already passing today but easy to break.

### Medium value, medium effort

4. **Playwright e2e for the map page.**
   - Navigate to `/`
   - Assert the canvas (`.mapboxgl-canvas`) is present and non-zero size
   - Assert at least one hex is hover-able (querySelector + simulated mousemove)
   - Click → assert popup appears + has at least one layer in the breakdown
   
   This would have caught the three Mapbox traps we hit (container 0-height, worker URL, paint memoization) **without** opening a browser manually.

5. **Migration check in CI.** GitHub Action that runs `supabase db diff` against a fresh Postgres container, ensures `supabase/migrations/*.sql` applies cleanly. Catches `001 → 002 → 007` ordering bugs early.

6. **Visual regression for tile output.** Snapshot a known z/x/y tile's MVT bytes; alert if it changes unexpectedly. Useful when refactoring the RPC or color expression.

### Lower priority

7. **Load test.** `vegeta attack http://localhost:3001/api/tiles/...` to measure throughput. Tile RPC will be the bottleneck; want to know capacity before launch.

8. **A11y / Lighthouse audit.** Run before any public release.

## Testing patterns to follow when adding tests

### Python (pipeline)

- Use `pytest` (in `modal/pyproject.toml`'s dev extras)
- Use a separate test DB (or sqlite-spatialite mock); never touch the live `uuqxqqcelabpacljeqgm`
- Place tests in `modal/tests/` mirroring `modal/prism/` structure
- Run: `conda run -n claude pytest modal/tests/`

### TypeScript (frontend + API)

- Use `vitest` (lightweight, fast). Don't pull Jest — Vitest is a drop-in replacement that works with our ESM setup.
- Place tests next to source as `*.test.ts` or in `tests/` dir
- Use `@testing-library/react` for components
- Run: `pnpm test`

### End-to-end (browser)

- `playwright` (not `cypress` — Playwright is the modern default and works on more browsers)
- Run against a local dev server in CI: `pnpm dev -p 3001 &; pnpm playwright test`
- Snapshot critical user flows: map loads, hex click → popup, filter toggle → tile refetch

## Manual test checklist for "is the pilot working"

Run before declaring "Phase 2 done":

1. `pnpm typecheck` — clean
2. `pnpm build` — clean
3. `pnpm dev -p 3001`, open `http://localhost:3001`
4. Map renders dark basemap of Vermont (~5 sec)
5. Console: `[PrismMap] init` log shows non-zero `containerSize`
6. Zoom in to ~14, find a populated area; hexes should be visible with color variation
7. Hover a hex → tooltip shows score + top layer name
8. Click a hex → popup loads layer breakdown within ~1 sec
9. Open the Layers panel → 131 layers grouped by category, status badges colored correctly
10. Switch basemap dark → light → satellite — hexes persist
11. Open the Filters panel — counties dropdown populates with VT counties
12. URL hash updates when you pan/zoom

All twelve should pass cleanly. If any fails, see [FRONTEND.md § debugging the map](./FRONTEND.md#debugging-the-map).
