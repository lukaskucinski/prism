"""
Lightweight clipping shim used by the lifted PEIT arcgis_query.py.

PEIT's `query_arcgis_layer` calls
    clip_geodataframe(gdf, clip_boundary, layer_name, geometry_type)
and expects `(clipped_gdf, metadata_dict)` back. PRISM only needs simple
intersection of features with a polygon AOI; GeoPandas' `clip()` is enough.
"""

from __future__ import annotations

import time

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


def clip_geodataframe(
    gdf: gpd.GeoDataFrame,
    clip_boundary: BaseGeometry,
    layer_name: str = "",
    geometry_type: str = "polygon",
) -> tuple[gpd.GeoDataFrame, dict]:
    """
    Intersect features in `gdf` with `clip_boundary`. Both must be EPSG:4326.

    Returns (clipped_gdf, metadata) where metadata mirrors PEIT's shape:
      { 'pre_clip_count', 'post_clip_count', 'clipped_count', 'clip_seconds' }
    """
    started = time.monotonic()
    pre = len(gdf)
    if gdf.empty or clip_boundary is None or clip_boundary.is_empty:
        return gdf, {
            "pre_clip_count": pre,
            "post_clip_count": pre,
            "clipped_count": 0,
            "clip_seconds": 0.0,
        }

    # Points: pass through (clip is a no-op semantically — features were already
    # filtered by intersects()). For polygons/lines, do a true geometric clip so
    # we don't drag features that extend past the AOI.
    if geometry_type == "point":
        clipped = gdf
    else:
        try:
            clipped = gpd.clip(gdf, clip_boundary, keep_geom_type=True)
        except Exception:
            # Fall back to intersection check only — better to keep features
            # whole than fail the entire layer ingest.
            clipped = gdf[gdf.geometry.intersects(clip_boundary)]

    if not clipped.empty:
        clipped = clipped[~clipped.geometry.is_empty]

    post = len(clipped)
    return clipped, {
        "pre_clip_count": pre,
        "post_clip_count": post,
        "clipped_count": pre - post,
        "clip_seconds": round(time.monotonic() - started, 3),
    }
