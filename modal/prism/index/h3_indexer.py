"""
H3 indexing primitives.

`features_to_r8_cells(gdf, geometry_type)` returns a list of (h3_index, feature_count)
tuples representing the R8 hexes covered by the features.

Polygon → h3.polygon_to_cells at res 8 (fills the interior).
Line → buffer by category-appropriate distance, then polygon_to_cells.
Point → latlng_to_cell at res 8 (single cell per point).
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

import geopandas as gpd
import h3
import pyproj
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from prism.log import get_logger

logger = get_logger(__name__)

BASE_RESOLUTION = 8

# Buffer distances for line features (meters) by category. Tuned to match
# typical permitting study widths.
LINE_BUFFER_METERS_DEFAULT = 152.4  # 500 ft
LINE_BUFFER_METERS_BY_CATEGORY = {
    "infrastructure": 152.4,  # 500 ft (pipelines, transmission)
    "floodplain_wetland": 100.0,  # narrower for waterway-likes
    "historic": 50.0,
}

_TO_WEB_MERCATOR = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
_TO_WGS84 = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform


def _buffer_meters_wgs84(geom: BaseGeometry, meters: float) -> BaseGeometry:
    """Buffer a WGS84 geometry by N meters via Web Mercator round-trip."""
    projected = transform(_TO_WEB_MERCATOR, geom)
    buffered = projected.buffer(meters)
    return transform(_TO_WGS84, buffered)


def _polygon_to_cells(poly: Polygon | MultiPolygon, res: int) -> Iterable[str]:
    """h3.polygon_to_cells across one Polygon or MultiPolygon."""
    if isinstance(poly, MultiPolygon):
        for sub in poly.geoms:
            yield from _polygon_to_cells(sub, res)
        return
    if poly.is_empty:
        return
    # h3 v4 expects [(lat,lng), ...] outer + holes
    exterior = [(y, x) for x, y in poly.exterior.coords]
    holes = [[(y, x) for x, y in interior.coords] for interior in poly.interiors]
    poly_obj = h3.LatLngPoly(exterior, *holes) if holes else h3.LatLngPoly(exterior)
    yield from h3.polygon_to_cells(poly_obj, res)


def _line_to_cells(line: BaseGeometry, res: int, buffer_meters: float) -> Iterable[str]:
    buffered = _buffer_meters_wgs84(line, buffer_meters)
    yield from _polygon_to_cells(buffered, res)


def _point_to_cell(point: Point, res: int) -> str:
    return h3.latlng_to_cell(point.y, point.x, res)


def features_to_r8_cells(
    gdf: gpd.GeoDataFrame,
    geometry_type: str,
    *,
    friction_category: str | None = None,
    res: int = BASE_RESOLUTION,
) -> list[tuple[str, int]]:
    """
    Reduce features to a list of (h3_index, feature_count) tuples at the given
    resolution. Duplicated cells across features within a single layer are
    aggregated into feature_count.
    """
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif str(gdf.crs).upper() not in ("EPSG:4326", "WGS84"):
        gdf = gdf.to_crs("EPSG:4326")

    counter: Counter[str] = Counter()
    line_buf = LINE_BUFFER_METERS_BY_CATEGORY.get(
        friction_category or "", LINE_BUFFER_METERS_DEFAULT
    )

    for geom in gdf.geometry:
        if geom is None or geom.is_empty:
            continue

        gtype = geom.geom_type
        try:
            if geometry_type == "polygon" or gtype in ("Polygon", "MultiPolygon"):
                for cell in _polygon_to_cells(geom, res):  # type: ignore[arg-type]
                    counter[cell] += 1
            elif geometry_type == "line" or gtype in ("LineString", "MultiLineString"):
                if isinstance(geom, MultiLineString):
                    for sub in geom.geoms:
                        for cell in _line_to_cells(sub, res, line_buf):
                            counter[cell] += 1
                elif isinstance(geom, LineString):
                    for cell in _line_to_cells(geom, res, line_buf):
                        counter[cell] += 1
            elif geometry_type == "point" or gtype in ("Point", "MultiPoint"):
                if isinstance(geom, MultiPoint):
                    for pt in geom.geoms:
                        counter[_point_to_cell(pt, res)] += 1
                elif isinstance(geom, Point):
                    counter[_point_to_cell(geom, res)] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipped feature: %s (%s)", exc, gtype)
            continue

    return [(h3_index, count) for h3_index, count in counter.items()]


def cell_polygon_wkt(h3_index: str) -> str:
    """Return the WKT polygon for an H3 cell in EPSG:4326."""
    boundary = h3.cell_to_boundary(h3_index)  # [(lat, lng), ...]
    coords = ", ".join(f"{lng} {lat}" for lat, lng in boundary)
    # Close the ring
    first_lat, first_lng = boundary[0]
    coords += f", {first_lng} {first_lat}"
    return f"POLYGON(({coords}))"
