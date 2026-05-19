"""
CLI: `python -m prism.ingest --states VT,NV`

Runs the layer ingest pipeline across all layers in prism_layers (or a subset
selected via --layers / --categories / --only-failed). Each layer is processed
independently; per-layer failures don't abort the run.
"""

from __future__ import annotations

import os
import sys
import time

import click

from prism.db import supabase_admin
from prism.ingest.layer_ingest import (
    IngestResult,
    fetch_layers,
    fetch_state_aoi,
    ingest_layer,
)
from prism.log import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--states",
    default=lambda: os.environ.get("PRISM_PILOT_STATES", "VT,NV"),
    help="Comma-separated state abbreviations defining the AOI.",
)
@click.option(
    "--layers",
    default=None,
    help="Comma-separated layer_ids to limit ingest to. Default: all in prism_layers.",
)
@click.option(
    "--categories",
    default=None,
    help="Comma-separated friction_category filter.",
)
@click.option("--only-failed", is_flag=True, help="Re-ingest only layers with ingest_status='failed'.")
@click.option("--only-pending", is_flag=True, help="Re-ingest only layers with ingest_status='pending'.")
@click.option("--limit", type=int, default=0, help="Cap the number of layers to attempt (debug).")
def cli(
    states: str,
    layers: str | None,
    categories: str | None,
    only_failed: bool,
    only_pending: bool,
    limit: int,
) -> None:
    abbrs = [s.strip().upper() for s in states.split(",") if s.strip()]
    logger.info("Ingest scope: states=%s", abbrs)

    aoi = fetch_state_aoi(abbrs)
    logger.info("AOI bounds: %s", aoi.bounds)

    # Layer selection
    only_layer_ids: list[str] | None = None
    if layers:
        only_layer_ids = [s.strip() for s in layers.split(",") if s.strip()]
    elif categories or only_failed or only_pending:
        sb = supabase_admin()
        q = sb.table("prism_layers").select("layer_id")
        if categories:
            q = q.in_("friction_category", [c.strip() for c in categories.split(",")])
        if only_failed:
            q = q.eq("ingest_status", "failed")
        if only_pending:
            q = q.eq("ingest_status", "pending")
        only_layer_ids = [r["layer_id"] for r in (q.execute().data or [])]

    all_layers = fetch_layers(only_layer_ids=only_layer_ids)
    if limit and limit > 0:
        all_layers = all_layers[:limit]

    if not all_layers:
        logger.warning("No layers selected; nothing to do.")
        return

    logger.info("Ingesting %d layers", len(all_layers))
    started = time.monotonic()
    results: list[IngestResult] = []
    for i, layer in enumerate(all_layers, start=1):
        logger.info("[%d/%d] %s", i, len(all_layers), layer.layer_name)
        res = ingest_layer(layer, aoi)
        results.append(res)

    elapsed = time.monotonic() - started
    succeeded = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    total_features = sum(r.features_processed for r in results)
    total_hexes = sum(r.hexes_written for r in results)

    logger.info("─" * 60)
    logger.info(
        "Ingest complete in %.1fs: %d ok, %d skipped, %d failed",
        elapsed,
        succeeded,
        skipped,
        failed,
    )
    logger.info("Total features processed: %d", total_features)
    logger.info("Total hex writes: %d", total_hexes)
    logger.info("Next: `python -m prism.score --aggregate`")


if __name__ == "__main__":
    sys.exit(cli(standalone_mode=False) or 0)
