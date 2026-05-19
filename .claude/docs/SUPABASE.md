# Supabase

PRISM lives in the **ITG** Supabase org. The HexRoute project (`llfnysraszaaolcxwsaj`) is in the same org for future cross-project work.

## Project

| Field | Value |
|---|---|
| Name | PRISM |
| Ref | `uuqxqqcelabpacljeqgm` |
| Org | ITG (`ziwfumqunyfyjueedrdw`) |
| Region | us-east-2 |
| Postgres | 17.6 |
| PostGIS | 3.3.7 |
| Plan | **Free tier — 500 MB disk cap** |
| URL | `https://uuqxqqcelabpacljeqgm.supabase.co` |

The Supabase MCP token currently has access to this org only. If anyone migrates the project to a different org, re-authenticate the MCP first.

## Schema

7 migrations under `supabase/migrations/`. Apply via `supabase db push` or paste into the Studio SQL editor.

| Migration | Purpose |
|---|---|
| `001_extensions.sql` | postgis + btree_gist in `extensions` schema |
| `002_layers.sql` | `prism_layers` catalog (131 rows seeded) |
| `003_hex_tables.sql` | `prism_hex_r8/r7/r6` with GIST+BTREE+GIN indexes |
| `004_hex_layer_join.sql` | `prism_hex_layer (h3_index, layer_id, feature_count)` join |
| `005_boundaries.sql` | `prism_states`, `prism_counties`, `prism_districts` (TIGER 2024) |
| `006_ingest_log.sql` | append-only pipeline audit log |
| `007_mvt_rpc.sql` | `prism_get_hex_mvt(z, x, y, filter_json)` MVT producer |

Layer catalog seed: `supabase/seed/prism_layers.sql` — generated from APPEIT's `layer_config_from_rest_noraw.json` via `scripts/build-seed-sql.mjs`. The Python loader `prism.seed.load_layers` does the same job; the SQL is a convenience for clean re-seeding without conda.

## Free-tier survival kit

### 500 MB hard cap

When the disk hits the cap, Supabase **automatically flips `default_transaction_read_only=on` at the project level** to protect the cluster. Symptoms:
- Writes fail with `ReadOnlySqlTransaction: cannot execute INSERT/UPDATE/TRUNCATE/DROP in a read-only transaction`
- Even MCP `execute_sql` (PostgREST) is blocked

Recovery requires freeing space, which itself requires writes. Two outs:

1. **Direct psycopg with session override.** TRUNCATE / DROP are space-freeing and Supabase usually allows them even in disk-full mode. Our `prism.db.pg_conn()` runs `SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE` on every connection — this overrides the project-level read-only setting for the session.

2. **Studio SQL editor.** Uses a privileged path that ignores read-only mode. Can run `ALTER DATABASE postgres SET default_transaction_read_only = off` to permanently lift the flag, but only useful after freeing disk first.

### `scripts/cleanup-for-vt-only.py`

Wipes hex tables (`prism_hex_layer`, `prism_hex_r8/r7/r6`), resets `prism_layers.ingest_status='pending'`, and VACUUM FULLs the hex tables to reclaim physical storage. Use this when you've over-ingested. Idempotent. Reports DB size before and after.

### Current sizing (VT-only pilot)

| Component | Size |
|---|---|
| `prism_hex_r8` (57,658 rows + GIST + BTREE + GIN) | ~45 MB |
| `prism_hex_layer` (72,142 rows + 2 indexes) | ~20 MB |
| `prism_hex_r7` + `prism_hex_r6` | ~5 MB |
| `prism_layers` + boundaries + log | ~25 MB |
| **Total** | **~95 MB** (19% of 500 MB cap) |

Adding another small state (DE, RI) is feasible. Adding NV would push past quota — use `--local-output` for those.

## Long-query gotchas

### TCP keepalive is required for any psycopg query > 30s

Supabase's connection pooler / load balancer kills idle TCP connections after ~30–60 seconds without traffic. A large `UPDATE` or `CREATE TABLE AS` query can run server-side for minutes while the client socket sits idle → the LB kills the connection → psycopg raises `SSL error: unexpected eof while reading`.

Fix in `prism/db.py::pg_conn()`:

```python
psycopg.connect(
    SUPABASE_DB_URL,
    keepalives=1,
    keepalives_idle=30,
    keepalives_interval=10,
    keepalives_count=5,
)
```

Plus chunk large operations into pieces that each complete in < 30s. The scorer uses 50k h3-index chunks. The aggregator does per-parent inserts (slow but small per-statement).

### Statement timeout

Default `statement_timeout` on Supabase is 2 minutes for `service_role`. For longer ops, `SET statement_timeout = '600s'` per session.

## Password URL-encoding

`SUPABASE_DB_URL` lives in `.env`. The password portion **must percent-encode all non-`[A-Za-z0-9._~-]` characters**. Common offenders: `/` → `%2F`, `!` → `%21`, `$` → `%24`, `)` → `%29`, `#` → `%23`, `@` → `%40`.

Why this matters beyond URL parsing: `$` in PowerShell or Bash is a variable-expansion trigger. If you ever paste the URL into a shell (e.g. `psql "$env:SUPABASE_DB_URL"`), un-encoded `$abc` becomes an empty string. Silent corruption.

Validator: `node scripts/check-db-url.mjs` — checks the URL structure and flags unsafe chars without echoing the password.

Easiest path: regenerate the DB password in the Supabase dashboard until it only contains alphanumerics.

## MVT RPC

`prism_get_hex_mvt(z, x, y, filter_json)` returns a single-layer MVT named `hex` with properties `h3_index`, `friction_score`, `layer_count`, `top_friction_driver`.

- Resolution by zoom: `z ≤ 6 → R6`, `z 7–9 → R7`, `z ≥ 10 → R8`
- Filters supported via `filter_json` JSONB: `s` (state abbrs), `c` (county FIPS), `d` (district IDs), `r` (score range `[lo, hi]`), `g` (category names)
- Granted to `service_role` only — Next.js admin client calls it

Tile route: `/api/tiles/v{N}/{z}/{x}/{y}.mvt?f={base64url(filterHash)}`. The `v{N}` segment is in the URL path so CDN cache busts cleanly when `NEXT_PUBLIC_TILE_VERSION` increments. Bump after every rescore.

## Diagnostics

| Script | Use |
|---|---|
| `scripts/diagnose-db-conn.py` | Reports host/port, `default_transaction_read_only`, `pg_is_in_recovery`, runs a write probe — useful when in doubt |
| `scripts/check-db-url.mjs` | Validates `.env` URL without echoing password |
| `scripts/cleanup-for-vt-only.py` | Wipe + VACUUM FULL the hex tables |

## RLS posture

All `prism_*` tables have RLS enabled. v1 has **no policies on writable tables** (only `prism_states`, `prism_counties`, `prism_districts` have `FOR SELECT USING (true)` policies for public reads). API routes use the service-role admin client, which bypasses RLS.

Phase 6 (paid feature) will add `auth.users`-backed policies on `prism_uploads`, `prism_analyses`, `prism_jobs` (tables not yet created — schema-scaffolded only). See [SECURITY](./SECURITY.md).
