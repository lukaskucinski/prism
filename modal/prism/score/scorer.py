"""
Placeholder friction scorer.

Reads weights from prism_layers, joins through prism_hex_layer, writes
denormalized friction_score, layer_count, top_friction_driver, and
category_flags onto prism_hex_r8.

Formula (v1, placeholder):
    friction_score = min(100, sum(friction_weight))
    where friction_weight is the per-layer numeric weight in prism_layers
    (defaulted from category tier: high=30, medium=15, low=5).

Replaceable: when the layer-evaluation task delivers real per-layer weights,
just re-run this script. No DB schema changes needed.

Usage:
    python -m prism.score                # rescore r8 (then run aggregator)
    python -m prism.score --aggregate    # also rebuild r7/r6
"""

from __future__ import annotations

import json
import sys

import click

from prism.db import pg_conn
from prism.index.aggregator import rebuild_r6, rebuild_r7
from prism.log import db_log, get_logger

logger = get_logger(__name__)


def rescore_r8() -> int:
    """
    Single SQL pass: aggregate the join table by hex and update the denormalized
    columns on prism_hex_r8. Fast even at 1M+ rows because everything is keyed.
    """
    sql = """
    WITH per_hex AS (
      SELECT
        hl.h3_index,
        LEAST(100.0, SUM(COALESCE(l.friction_weight, 0)))::real AS friction_score,
        COUNT(DISTINCT hl.layer_id)::int AS layer_count,
        (
          SELECT l2.layer_name
          FROM prism_hex_layer hl2
          JOIN prism_layers l2 ON l2.layer_id = hl2.layer_id
          WHERE hl2.h3_index = hl.h3_index
          ORDER BY COALESCE(l2.friction_weight, 0) DESC
          LIMIT 1
        ) AS top_friction_driver,
        jsonb_object_agg(l.friction_category, true) AS category_flags
      FROM prism_hex_layer hl
      JOIN prism_layers l ON l.layer_id = hl.layer_id
      GROUP BY hl.h3_index
    )
    UPDATE prism_hex_r8 r
       SET friction_score = ph.friction_score,
           layer_count = ph.layer_count,
           top_friction_driver = ph.top_friction_driver,
           category_flags = ph.category_flags,
           updated_at = now()
      FROM per_hex ph
     WHERE r.h3_index = ph.h3_index
    RETURNING r.h3_index;
    """
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        affected = cur.rowcount
        conn.commit()
    logger.info("Rescored %d R8 hexes", affected)
    return affected


@click.command()
@click.option("--aggregate", is_flag=True, help="Also rebuild R7/R6 aggregates after rescoring R8.")
def cli(aggregate: bool) -> None:
    r8 = rescore_r8()
    payload = {"r8": r8}
    if aggregate:
        r7 = rebuild_r7()
        r6 = rebuild_r6()
        payload.update({"r7": r7, "r6": r6})
        logger.info("Aggregated → R7=%d, R6=%d", r7, r6)
    db_log(
        layer_id=None,
        action="score",
        status="ok",
        features_processed=r8,
        message=f"Rescored R8={r8}" + (f", R7/R6 rebuilt" if aggregate else ""),
        payload=payload,
    )


if __name__ == "__main__":
    sys.exit(cli(standalone_mode=False) or 0)
