"""
Aggregate prism_hex_r8 → prism_hex_r7 → prism_hex_r6.

Each parent hex inherits:
- friction_score := max(child friction_scores)
- layer_count := number of distinct layers across all child hexes
- top_friction_driver := layer name with the highest aggregate contribution
- category_flags := OR of children
- geom := H3 cell polygon at parent resolution

Written as a full rebuild (TRUNCATE + INSERT) since the aggregate tables are
small (~10k rows for VT+NV at R6+R7 combined).
"""

from __future__ import annotations

from typing import Iterable

import h3

from prism.db import pg_conn
from prism.index.h3_indexer import cell_polygon_wkt
from prism.log import db_log, get_logger

logger = get_logger(__name__)


def _parents(cells: Iterable[str], parent_res: int) -> set[str]:
    return {h3.cell_to_parent(c, parent_res) for c in cells}


def rebuild_r7() -> int:
    return _rebuild_parent_table(child_res=8, parent_res=7, parent_table="prism_hex_r7")


def rebuild_r6() -> int:
    return _rebuild_parent_table(child_res=7, parent_res=6, parent_table="prism_hex_r6")


def _rebuild_parent_table(child_res: int, parent_res: int, parent_table: str) -> int:
    child_table = f"prism_hex_r{child_res}"
    logger.info("Rebuilding %s from %s", parent_table, child_table)
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {parent_table}")
        # Fetch all child rows, group by parent in Python (parent table is small)
        cur.execute(
            f"SELECT h3_index, friction_score, layer_count, top_friction_driver, "
            f"category_flags FROM {child_table}"
        )
        rows = cur.fetchall()
        if not rows:
            conn.commit()
            return 0

        # Group: parent_h3 → list of children
        groups: dict[str, list[tuple]] = {}
        for r in rows:
            parent = h3.cell_to_parent(r[0], parent_res)
            groups.setdefault(parent, []).append(r)

        for parent_h3, children in groups.items():
            max_score = max((c[1] or 0) for c in children)
            agg_layer_count = max((c[2] or 0) for c in children)
            # Driver: most-frequent top_friction_driver in children
            drivers: dict[str, int] = {}
            for c in children:
                if c[3]:
                    drivers[c[3]] = drivers.get(c[3], 0) + 1
            top_driver = max(drivers, key=drivers.get) if drivers else None
            # OR category_flags
            merged_flags: dict[str, bool] = {}
            for c in children:
                flags = c[4] or {}
                for k, v in flags.items():
                    if v:
                        merged_flags[k] = True

            cur.execute(
                f"""
                INSERT INTO {parent_table} (h3_index, friction_score, layer_count, top_friction_driver, category_flags, geom)
                VALUES (%s, %s, %s, %s, %s::jsonb, ST_GeomFromText(%s, 4326))
                ON CONFLICT (h3_index) DO UPDATE
                  SET friction_score = EXCLUDED.friction_score,
                      layer_count = EXCLUDED.layer_count,
                      top_friction_driver = EXCLUDED.top_friction_driver,
                      category_flags = EXCLUDED.category_flags,
                      geom = EXCLUDED.geom,
                      updated_at = now()
                """,
                (
                    parent_h3,
                    max_score,
                    agg_layer_count,
                    top_driver,
                    __import__("json").dumps(merged_flags),
                    cell_polygon_wkt(parent_h3),
                ),
            )
        conn.commit()
    logger.info("%s: %d rows", parent_table, len(groups))
    return len(groups)


def main() -> int:
    r7 = rebuild_r7()
    r6 = rebuild_r6()
    db_log(
        layer_id=None,
        action="aggregate",
        status="ok",
        features_processed=r7 + r6,
        message=f"Aggregated to {r7} R7 hexes, {r6} R6 hexes",
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
