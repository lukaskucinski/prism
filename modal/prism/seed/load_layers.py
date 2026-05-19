"""
Seed prism_layers from APPEIT's layers_config.json (205 entries).

Usage:
    python -m prism.seed.load_layers

Idempotent — uses UPSERT keyed by layer_id. Re-running picks up edits to the
catalog without duplicating rows.

The layer_id PK is derived as `{service_name}-{sublayer_id}` so it remains
stable across catalog rebuilds.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from prism.categories import (
    CATEGORY_DEFAULT_TIER,
    category_for,
    default_weight_for,
)
from prism.db import supabase_admin
from prism.log import db_log, get_logger

logger = get_logger(__name__)

CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "layers_config.json"


def _service_parts(url: str) -> tuple[str, str]:
    """
    Walk URL path backward to find FeatureServer/MapServer suffix. Returns
    (service_name, service_type). Handles nested paths.

    Examples:
      services/NPS_Land_Permitting_Layer/FeatureServer
        → ("NPS_Land_Permitting_Layer", "FeatureServer")
      services/TIGERweb/AIANNHA/MapServer
        → ("AIANNHA", "MapServer")
    """
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    for i, seg in enumerate(parts):
        if seg in ("FeatureServer", "MapServer"):
            return (parts[i - 1] if i > 0 else "unknown", seg)
    return (parts[-1] if parts else "unknown", "FeatureServer")


def _make_layer_id(name: str, service_name: str, sublayer_id: int) -> str:
    """
    Stable, human-readable PK. Mirrors scripts/build-seed-sql.mjs.

    Format: {name_slug}__{service_slug}-{sublayer_id}
    """
    name_slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()[:60]
    service_slug = re.sub(r"[^A-Za-z0-9_]+", "_", service_name).strip("_")
    return f"{name_slug}__{service_slug}-{sublayer_id}"


def main() -> int:
    if not CATALOG_PATH.exists():
        logger.error("Catalog not found at %s", CATALOG_PATH)
        return 1

    with CATALOG_PATH.open(encoding="utf-8") as f:
        catalog = json.load(f)

    if not isinstance(catalog, list):
        logger.error("Catalog root must be a list, got %s", type(catalog).__name__)
        return 1

    rows: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for entry in catalog:
        try:
            name = entry["name"]
            url = entry["url"]
            sublayer_id = int(entry.get("layer_id", 0))
            geometry_type = entry["geometry_type"].lower()
            raw_group = entry.get("group", "")
            description = entry.get("description", "") or None
        except (KeyError, ValueError, TypeError) as exc:
            skipped.append((str(entry.get("name", "?")), f"missing field: {exc}"))
            continue

        if geometry_type not in ("polygon", "point", "line"):
            skipped.append((name, f"unsupported geometry_type: {geometry_type}"))
            continue

        service_name, service_type = _service_parts(url)
        layer_id = _make_layer_id(name, service_name, sublayer_id)
        category = category_for(raw_group)
        tier = CATEGORY_DEFAULT_TIER[category]

        rows.append(
            {
                "layer_id": layer_id,
                "layer_name": name,
                "raw_group": raw_group,
                "friction_category": category,
                "source_url": url,
                "source_layer_id": sublayer_id,
                "service_type": service_type,
                "geometry_type": geometry_type,
                "friction_weight": default_weight_for(category),
                "friction_tier": tier,
                "description": description,
            }
        )

    if not rows:
        logger.error("No valid rows parsed from catalog")
        return 1

    # Upsert in batches
    sb = supabase_admin()
    BATCH = 100
    inserted = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        resp = sb.table("prism_layers").upsert(chunk, on_conflict="layer_id").execute()
        inserted += len(resp.data) if resp.data else len(chunk)

    logger.info(
        "Seeded prism_layers: %d rows upserted, %d skipped",
        inserted,
        len(skipped),
    )
    if skipped:
        for name, reason in skipped[:10]:
            logger.warning("  skipped %s: %s", name, reason)
        if len(skipped) > 10:
            logger.warning("  ... and %d more", len(skipped) - 10)

    db_log(
        layer_id=None,
        action="seed",
        status="ok" if not skipped else "warn",
        features_processed=inserted,
        message=f"Seeded {inserted} layers; skipped {len(skipped)}",
        payload={"skipped_samples": skipped[:20]},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
