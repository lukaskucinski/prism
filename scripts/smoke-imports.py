"""Verify all PRISM pipeline modules import without errors."""

print("Importing prism modules...")
import prism
import prism.db
import prism.log
import prism.categories
import prism.boundaries.load_tiger
import prism.ingest.arcgis_query
import prism.ingest.geometry_converters
import prism.ingest.clipping
import prism.ingest.layer_ingest
import prism.index.h3_indexer
import prism.index.aggregator
import prism.score.scorer

print("All modules imported OK.")
print(f"prism version: {prism.__version__}")

# Verify .env was loaded
import os
print("---")
for k in (
    "NEXT_PUBLIC_SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_DB_URL",
    "NEXT_PUBLIC_MAPBOX_TOKEN",
    "PRISM_PILOT_STATES",
):
    v = os.environ.get(k, "")
    if "URL" in k or "TOKEN" in k or "KEY" in k:
        masked = v[:12] + "..." + v[-6:] if v and len(v) > 20 else ("(set)" if v else "(EMPTY)")
        print(f"  {k}: {masked}")
    else:
        print(f"  {k}: {v}")

# Try a DB ping
print("---")
print("Pinging Supabase via psycopg...")
try:
    from prism.db import pg_conn

    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database(), current_user, version()")
        row = cur.fetchone()
        print(f"  db={row[0]}, user={row[1]}")
        print(f"  pg version={row[2][:80]}...")
        cur.execute("SELECT count(*) FROM prism_layers")
        print(f"  prism_layers count: {cur.fetchone()[0]}")
    print("DB connection OK.")
except Exception as e:
    print(f"DB connection FAILED: {type(e).__name__}: {e}")
    raise SystemExit(1)
