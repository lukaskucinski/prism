"""
Wipe hex tables to free Supabase disk, reset prism_layers ingest status.
Used when pivoting scope (e.g., VT-only after free-tier overflow).
Idempotent. Prints sizes before & after.
"""
from prism.db import pg_conn

with pg_conn() as conn, conn.cursor() as cur:
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"DB size before: {cur.fetchone()[0]}")

    print("Truncating prism_hex_layer, prism_hex_r8, prism_hex_r7, prism_hex_r6...")
    cur.execute("TRUNCATE TABLE prism_hex_layer, prism_hex_r8, prism_hex_r7, prism_hex_r6 CASCADE")

    print("Resetting prism_layers.ingest_status to 'pending'...")
    cur.execute(
        """
        UPDATE prism_layers
           SET ingest_status='pending',
               last_ingest_error=NULL,
               last_ingested=NULL,
               feature_count=0
        """
    )

    # Drop the scratch table from the failed scorer run (if any)
    cur.execute("DROP TABLE IF EXISTS prism_hex_score_tmp")

    conn.commit()

# VACUUM FULL must run outside a transaction block
conn = pg_conn()
conn.autocommit = True
with conn.cursor() as cur:
    for t in ("prism_hex_r8", "prism_hex_r7", "prism_hex_r6", "prism_hex_layer"):
        print(f"VACUUM FULL {t} ...")
        cur.execute(f"VACUUM (FULL, ANALYZE) {t}")
conn.close()

with pg_conn() as conn, conn.cursor() as cur:
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"DB size after:  {cur.fetchone()[0]}")
print("Cleanup OK.")
