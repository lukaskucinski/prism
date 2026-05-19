"""
CLI: `python -m prism.ingest --states VT,NV`

Runs the layer ingest pipeline across all layers in prism_layers (or a subset
selected via --layers / --categories / --only-failed). Each layer is processed
once **per state** (per-state AOI keeps ArcGIS polygon-mode queries efficient
and avoids the huge-bbox-envelope false-positive problem). Per-layer failures
don't abort the run.
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
    fetch_state_aois,
    ingest_layer,
)
from prism.ingest.local_sink import LocalSink
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
@click.option(
    "--local-output",
    "local_output",
    type=click.Path(dir_okay=False, path_type=str),
    default=None,
    help=(
        "Write hex + join results to a local GeoPackage instead of Supabase. "
        "Use for analytical-scope states (e.g. NV) that would overflow the "
        "free-tier DB quota."
    ),
)
def cli(
    states: str,
    layers: str | None,
    categories: str | None,
    only_failed: bool,
    only_pending: bool,
    limit: int,
    local_output: str | None,
) -> None:
    abbrs = [s.strip().upper() for s in states.split(",") if s.strip()]
    logger.info("Ingest scope: states=%s", abbrs)

    state_aois = fetch_state_aois(abbrs)
    for abbr, geom in state_aois.items():
        logger.info("  %s AOI bounds: %s", abbr, geom.bounds)

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

    total_units = len(all_layers) * len(state_aois)
    sink_label = f" → local {local_output}" if local_output else " → Supabase"
    logger.info(
        "Ingesting %d layers × %d states = %d units%s",
        len(all_layers),
        len(state_aois),
        total_units,
        sink_label,
    )

    local_sink = LocalSink(local_output) if local_output else None
    started = time.monotonic()
    results: list[IngestResult] = []
    unit = 0
    for layer in all_layers:
        layer_features = 0
        layer_hexes = 0
        layer_statuses: list[str] = []
        layer_errors: list[str] = []
        for abbr, aoi in state_aois.items():
            unit += 1
            logger.info("[%d/%d] %s  (%s)", unit, total_units, layer.layer_name, abbr)
            res = ingest_layer(layer, aoi, local_sink=local_sink)
            results.append(res)
            layer_features += res.features_processed
            layer_hexes += res.hexes_written
            layer_statuses.append(res.status)
            if res.error:
                layer_errors.append(f"{abbr}: {res.error}")

        logger.info(
            "  → layer rollup: features=%d hexes=%d states=%s",
            layer_features,
            layer_hexes,
            ",".join(f"{a}:{s[:3]}" for a, s in zip(state_aois, layer_statuses)),
        )

    if local_sink is not None:
        local_sink.close()

    elapsed = time.monotonic() - started
    succeeded = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    total_features = sum(r.features_processed for r in results)
    total_hexes = sum(r.hexes_written for r in results)

    logger.info("─" * 60)
    logger.info(
        "Ingest complete in %.1fs: %d ok, %d skipped, %d failed (across all layer×state units)",
        elapsed,
        succeeded,
        skipped,
        failed,
    )
    logger.info("Total features processed: %d", total_features)
    logger.info("Total hex writes: %d", total_hexes)
    if local_sink is not None:
        logger.info("Local output: %s", local_sink.path)
    else:
        logger.info("Next: `python -m prism.score --aggregate`")


if __name__ == "__main__":
    sys.exit(cli(standalone_mode=False) or 0)
