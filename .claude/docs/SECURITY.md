# Security

Threat model is light for v1 (public read-only map, no user data, no payments). Heavier posture comes with Phase 6 (paid feature + auth).

## Current posture (v1)

- **No authentication.** The map is publicly readable. Matches HexRoute's pattern.
- **No user data collected.** Filter state lives in browser URL only — never sent to a server.
- **No payments.** Stripe / billing comes in Phase 6.
- **Static (read-only) data.** Pipeline writes from local dev; production users only read.

## Secrets

Stored in `.env` only. `.env` is in `.gitignore`; tracked file is `.env.example` (no secrets).

| Secret | Scope | Rotation |
|---|---|---|
| `SUPABASE_SERVICE_ROLE_KEY` | Server only — never sent to client | Manual via Supabase dashboard |
| `SUPABASE_DB_URL` (password) | Server only (Python pipeline + Next.js admin client) | Manual via Supabase dashboard → Database |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public — embedded in client bundle | Public; harmless if leaked (RLS gate) |
| `NEXT_PUBLIC_MAPBOX_TOKEN` (`pk.*`) | Public — embedded in client bundle | URL-restricted to `localhost:3000`, `:3001`. Rotate if observed abuse. |
| `NEXT_PUBLIC_TILE_VERSION` | Non-secret. Public. Bumped after rescore for cache busting. | n/a |

If `.env` is ever committed by accident, **immediately** rotate `SUPABASE_SERVICE_ROLE_KEY` and the database password in the dashboard, then rewrite git history (or destroy + recreate the repo if the leak is on GitHub).

## RLS (Row-Level Security)

All `prism_*` tables have RLS **enabled** at the table level. Policy attachments vary:

| Table | Policy |
|---|---|
| `prism_states`, `prism_counties`, `prism_districts` | `FOR SELECT USING (true)` — public read of boundaries |
| `prism_layers`, `prism_hex_r6/r7/r8`, `prism_hex_layer`, `prism_ingest_log` | **No policies** — RLS denies all by default |

The Next.js API routes use the **admin client** (`createAdminClient()` → uses `SUPABASE_SERVICE_ROLE_KEY`) which bypasses RLS. This is the same pattern as HexRoute. Anon clients (in-browser direct queries) cannot read these tables.

The Python pipeline uses **direct psycopg with the postgres superuser** (`SUPABASE_DB_URL`), also RLS-bypass. Reserved for server-side use.

Result: data is functionally read-only to the public, exposed only via curated API routes and the MVT RPC.

## API surface

| Route | What it returns | Risk |
|---|---|---|
| `/api/tiles/v{N}/{z}/{x}/{y}.mvt` | MVT bytes — hex polygons + friction scores | Low. Public friction data. |
| `/api/hex/{h3_index}` | Layer breakdown for a single hex | Low. Same data, different shape. |
| `/api/layers` | Catalog of layers | Low. Public reference info. |
| `/api/states`, `/api/counties`, `/api/districts` | Boundary metadata (no geom) | Low. Census public data. |

Concerns:
- **No rate limiting.** Public endpoints could be DDoS'd or scraped. CDN caching (Vercel/Cloudflare) absorbs most of this. Plan to add basic per-IP rate limiting in `middleware.ts` before launch.
- **No CORS allowlist.** Currently `Access-Control-Allow-Origin: *` on the tile route. Fine for v1 (we want HexRoute to consume tiles). Lock down later if needed.

## Service-role key boundary

The service-role key must **never** appear in the client bundle. Code-level enforcement:

- `lib/supabase/client.ts` — uses anon key only. Imports are safe in client components.
- `lib/supabase/server.ts` — uses service-role key. Only imported from API routes (server components / route handlers). Never imported into a `"use client"` file.

If you add a new server module that uses the admin client, **do not** import it from a Client Component or any file with `"use client"`. Next.js will warn at build time, but it's easy to miss.

## Polygon upload (Phase 3, not yet wired)

When the file-parser UI ships:
- Hard limit: 5 MB file size, 200k vertex hard reject, 50k vertex warning + simplify
- Parse client-side — never send raw shapefile/KML to the server
- Sanitize: reject features with no geometry, infinite coordinates, or self-intersecting polygons

These limits are documented in the spec but not enforced yet. Don't ship Phase 3 without them.

## Mapbox token URL restrictions

Mapbox tokens (`pk.*`) are public by design. URL restrictions are a soft control — Mapbox checks the `Referer` header against an allowlist. Current allowlist:

- `http://localhost:3000/`
- `http://localhost:3001/`

Before production launch, add:
- `https://prism.kucimaps.com/`
- `https://*.vercel.app/` (preview deployments) — only if needed; ideally use a separate token for previews

If the token is hit from non-allowlisted origins, Mapbox returns 401 / 403 on tile + style requests. Map will be black with quiet errors in the browser console. Always whitelist the production origin before flipping the DNS over.

## Postgres password URL-encoding

The DB password in `SUPABASE_DB_URL` must encode all `/`, `?`, `#`, `@`, `&`, `=`, `+`, `!`, `$`, `(`, `)`, and any whitespace. Failure mode: silently wrong connection string. Tools:

- `node scripts/check-db-url.mjs` — flags unsafe chars without echoing the password
- Easier: generate DB passwords with only `[A-Za-z0-9._-]` from the dashboard

## Phase 6 readiness (forward-looking)

When we wire auth + Stripe:

1. Enable Supabase Auth (email or OAuth). Email-magic-link is cheapest.
2. Migrations: add `user_id UUID REFERENCES auth.users(id)` to `prism_uploads`, `prism_analyses`, `prism_jobs` (tables don't exist yet — schema-scaffolded only).
3. RLS policies: per-table `FOR ALL USING (user_id = auth.uid())`.
4. Stripe webhook handler with signing-secret verification — never trust the webhook payload without verifying.
5. Replace PEIT's brittle Modal-Dict rate limiting with a Supabase `prism_rate_limits` table + daily reset.

Reference: PEIT Map Creator's auth setup in `c:\Users\lukas\OneDrive\OSIT\Python\APPEIT\appeit_map_creator\peit-app-homepage\supabase\migrations\`.

## Audit log

`prism_ingest_log` is append-only and records every pipeline event (query / convert / h3_index / aggregate / score / error / clean). It's an auditable trail of what data went where, when. Useful for any future "we said we ingested X — prove it" question.
