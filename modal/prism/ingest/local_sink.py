"""
Local GeoPackage sink for ingest results that should NOT go to Supabase.

Use case: analytical ingests for larger states (e.g. Nevada) that would blow
through the free-tier disk quota if pushed to Supabase. The local file can
be read back with geopandas / DuckDB-spatial for offline analysis.

Layers written to the GPKG:
  - prism_hexes_r8  : (h3_index TEXT PK, geom Polygon)  — one row per hex
  - prism_hex_layer : (h3_index TEXT, layer_id TEXT, layer_name TEXT,
                       friction_category TEXT, feature_count INT)
                      — non-geometric attribute table

The schema mirrors the Supabase tables so the same downstream analysis works
either way.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import from_wkt
from shapely.geometry.base import BaseGeometry

from prism.index.h3_indexer import cell_polygon_wkt
from prism.log import get_logger

logger = get_logger(__name__)


class LocalSink:
    """
    Append-only GeoPackage writer.

    First write to each layer creates it; subsequent writes append. We keep
    track of the seen h3 indexes in-memory so that the per-hex geom is only
    written once even when many ArcGIS layers intersect the same hex.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_h3: set[str] = set()
        self._hex_buf: list[tuple[str, BaseGeometry]] = []
        self._join_buf: list[dict] = []
        self._FLUSH_EVERY = 25_000

    def add_layer_hits(
        self,
        layer_id: str,
        layer_name: str,
        friction_category: str,
        cell_counts: list[tuple[str, int]],
    ) -> int:
        """Buffer hex + join rows for a single ArcGIS layer's hits."""
        for h3, n in cell_counts:
            if h3 not in self._seen_h3:
                self._seen_h3.add(h3)
                self._hex_buf.append((h3, from_wkt(cell_polygon_wkt(h3))))
            self._join_buf.append(
                {
                    "h3_index": h3,
                    "layer_id": layer_id,
                    "layer_name": layer_name,
                    "friction_category": friction_category,
                    "feature_count": n,
                }
            )
        if len(self._hex_buf) >= self._FLUSH_EVERY or len(self._join_buf) >= self._FLUSH_EVERY:
            self.flush()
        return len(cell_counts)

    def flush(self) -> None:
        """Append in-memory buffers to the GPKG file."""
        if self._hex_buf:
            gdf = gpd.GeoDataFrame(
                {"h3_index": [h for h, _ in self._hex_buf]},
                geometry=[g for _, g in self._hex_buf],
                crs="EPSG:4326",
            )
            mode = "a" if self.path.exists() else "w"
            gdf.to_file(self.path, layer="prism_hexes_r8", driver="GPKG", mode=mode)
            logger.debug("Flushed %d hex rows", len(self._hex_buf))
            self._hex_buf.clear()

        if self._join_buf:
            df = pd.DataFrame(self._join_buf)
            # GPKG can hold non-spatial tables too
            mode = "a" if self.path.exists() else "w"
            # geopandas requires a geometry for to_file; use pyogrio for non-spatial
            try:
                import pyogrio

                pyogrio.write_dataframe(
                    df,
                    self.path,
                    layer="prism_hex_layer",
                    driver="GPKG",
                    append=(mode == "a"),
                )
            except ImportError:
                # Fallback: write CSV alongside GPKG
                csv_path = self.path.with_suffix(".hex_layer.csv")
                df.to_csv(csv_path, mode="a", header=not csv_path.exists(), index=False)
                logger.warning("pyogrio unavailable; wrote join rows to %s instead", csv_path)
            self._join_buf.clear()

    def close(self) -> None:
        self.flush()
        logger.info("LocalSink closed: %s (%d unique hexes)", self.path, len(self._seen_h3))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
