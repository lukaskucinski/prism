"""
Lightweight clipping shim used by the lifted PEIT arcgis_query.py.

PRISM only needs simple clipping of features to a polygon AOI (the union of
pilot-state boundaries). PEIT's full buffer-and-clip flow is overkill here;
GeoPandas' built-in `clip()` is sufficient.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


def clip_geodataframe(
    gdf: gpd.GeoDataFrame,
    clip_geom: BaseGeometry,
    *,
    keep_geom_type: bool = True,
) -> gpd.GeoDataFrame:
    """
    Clip features in `gdf` to `clip_geom`. Both must be in the same CRS.
    Returns a new GeoDataFrame; empty if no features intersect.
    """
    if gdf.empty:
        return gdf
    clipped = gpd.clip(gdf, clip_geom, keep_geom_type=keep_geom_type)
    # gpd.clip can occasionally introduce GeometryCollection; explode them
    if not clipped.empty:
        clipped = clipped[~clipped.geometry.is_empty]
    return clipped
