"""Probe the SUPABASE_DB_URL connection characteristics without echoing the password."""
import os
from urllib.parse import urlparse
from prism.db import pg_conn
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("SUPABASE_DB_URL", "")
p = urlparse(url)
print(f"host: {p.hostname}")
print(f"port: {p.port}")
print(f"path: {p.path}")
print(f"pooler? {'pooler' in (p.hostname or '')}")

with pg_conn() as conn, conn.cursor() as cur:
    cur.execute("SHOW default_transaction_read_only")
    print(f"default_transaction_read_only: {cur.fetchone()[0]}")
    cur.execute("SHOW transaction_read_only")
    print(f"transaction_read_only:        {cur.fetchone()[0]}")
    cur.execute("SELECT current_setting('server_version'), pg_is_in_recovery()")
    ver, in_recovery = cur.fetchone()
    print(f"server_version:               {ver}")
    print(f"pg_is_in_recovery:            {in_recovery}  ({'STANDBY/READ-REPLICA' if in_recovery else 'PRIMARY'})")
    cur.execute("SELECT current_user, session_user")
    cu, su = cur.fetchone()
    print(f"current_user / session_user:  {cu} / {su}")
    # Try a tiny write to confirm
    try:
        cur.execute("CREATE TEMP TABLE _probe (x int)")
        cur.execute("INSERT INTO _probe VALUES (1)")
        conn.commit()
        print("write probe:                  OK")
    except Exception as e:
        conn.rollback()
        print(f"write probe FAILED:           {type(e).__name__}: {e}")
