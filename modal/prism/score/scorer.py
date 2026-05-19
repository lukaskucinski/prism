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


def rescore_r8(chunk_size: int = 50_000) -> int:
    """
    Chunked rescore: builds per-hex aggregates into an unlogged scratch table
    in batches of `chunk_size` distinct h3 indexes per chunk, then does a
    single UPDATE join at the end.

    Why chunked: a single GROUP BY over the full prism_hex_layer (~1M rows
    × N layer joins) holds an open connection too long for Supabase's
    pooler. Each chunk completes in a few seconds, keeping the transaction
    short and the connection responsive.
    """
    logger.info("Computing per-hex aggregates (chunk=%d)", chunk_size)
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")

        cur.execute("DROP TABLE IF EXISTS prism_hex_score_tmp")
        cur.execute(
            """
            CREATE UNLOGGED TABLE prism_hex_score_tmp (
              h3_index            TEXT PRIMARY KEY,
              friction_score      REAL,
              layer_count         INT,
              top_friction_driver TEXT,
              category_flags      JSONB
            )
            """
        )
        conn.commit()

        # Iterate hexes in chunks. Use ROW_NUMBER for stable batching.
        cur.execute("SELECT count(DISTINCT h3_index) FROM prism_hex_layer")
        total = cur.fetchone()[0]
        logger.info("  %d distinct hexes to score", total)

        processed = 0
        offset = 0
        while True:
            cur.execute(
                """
                WITH batch AS (
                  SELECT DISTINCT h3_index
                    FROM prism_hex_layer
                   ORDER BY h3_index
                   OFFSET %s LIMIT %s
                )
                INSERT INTO prism_hex_score_tmp
                  (h3_index, friction_score, layer_count, top_friction_driver, category_flags)
                SELECT
                  hl.h3_index,
                  LEAST(100.0, SUM(COALESCE(l.friction_weight, 0)))::real,
                  COUNT(DISTINCT hl.layer_id)::int,
                  (array_agg(l.layer_name ORDER BY COALESCE(l.friction_weight, 0) DESC))[1],
                  jsonb_object_agg(l.friction_category, true)
                FROM prism_hex_layer hl
                JOIN prism_layers l ON l.layer_id = hl.layer_id
                WHERE hl.h3_index IN (SELECT h3_index FROM batch)
                GROUP BY hl.h3_index
                """,
                (offset, chunk_size),
            )
            inserted = cur.rowcount
            conn.commit()
            processed += inserted
            logger.info(
                "  chunk offset=%d inserted=%d total=%d/%d",
                offset,
                inserted,
                processed,
                total,
            )
            if inserted < chunk_size:
                break
            offset += chunk_size

        logger.info("Updating prism_hex_r8 from scratch table...")
        cur.execute(
            """
            UPDATE prism_hex_r8 r
               SET friction_score      = s.friction_score,
                   layer_count         = s.layer_count,
                   top_friction_driver = s.top_friction_driver,
                   category_flags      = s.category_flags,
                   updated_at          = now()
              FROM prism_hex_score_tmp s
             WHERE r.h3_index = s.h3_index
            """
        )
        affected = cur.rowcount
        conn.commit()

        cur.execute("DROP TABLE prism_hex_score_tmp")
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
