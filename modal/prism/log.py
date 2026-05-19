"""
Stdlib logging + optional database logging to prism_ingest_log.

`get_logger(name)` returns a configured Python logger that writes to stderr
with timestamps. Pipeline modules use `db_log()` to additionally write
structured rows to the prism_ingest_log table.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

_LOG_LEVEL = os.environ.get("PRISM_LOG_LEVEL", "INFO").upper()
_LOG_FMT = "%(asctime)s [%(levelname)-7s] %(name)s :: %(message)s"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FMT))
    logger.addHandler(handler)
    logger.setLevel(_LOG_LEVEL)
    logger.propagate = False
    return logger


def db_log(
    layer_id: Optional[str],
    action: str,
    status: str,
    *,
    duration_ms: Optional[int] = None,
    features_processed: Optional[int] = None,
    hexes_written: Optional[int] = None,
    message: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Append a row to prism_ingest_log. Best-effort — never raise on log errors."""
    from prism.db import supabase_admin

    try:
        client = supabase_admin()
        client.table("prism_ingest_log").insert(
            {
                "layer_id": layer_id,
                "action": action,
                "status": status,
                "duration_ms": duration_ms,
                "features_processed": features_processed,
                "hexes_written": hexes_written,
                "message": message,
                "payload": payload,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        get_logger(__name__).warning("db_log failed: %s", exc)
