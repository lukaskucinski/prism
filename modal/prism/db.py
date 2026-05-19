"""
Database helpers.

`supabase_admin()` returns a service-role Supabase client (singleton).
`pg_conn()` returns a raw psycopg connection, used for fast bulk COPY/INSERT
of hex polygons and join rows where the supabase-py client would be slow.

Env vars (loaded from .env.local at the repo root, or from process env):
  NEXT_PUBLIC_SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_DB_URL
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from supabase import Client, create_client

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    for candidate in (_REPO_ROOT / ".env.local", _REPO_ROOT / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


_load_env()


def required(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required env var: {name}. Set it in .env.local at the repo root."
        )
    return val


@lru_cache(maxsize=1)
def supabase_admin() -> Client:
    url = required("NEXT_PUBLIC_SUPABASE_URL")
    key = required("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def pg_conn() -> psycopg.Connection:
    """
    Direct psycopg connection. Use for fast bulk operations (COPY, executemany).
    Caller is responsible for closing.
    """
    return psycopg.connect(required("SUPABASE_DB_URL"), autocommit=False)
