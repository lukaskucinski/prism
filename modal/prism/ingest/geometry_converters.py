"""
Geometry conversion utilities for PEIT Map Creator.

This module provides functions to convert between ESRI JSON and GeoJSON formats,
as well as utilities for geometry simplification and vertex counting.

ArcGIS FeatureServers return geometries in ESRI JSON format, which needs to be
converted to standard GeoJSON for use with GeoPandas and Folium. Additionally,
when sending spatial queries, Shapely geometries need to be converted to ESRI JSON.

Functions:
    convert_esri_point: Convert ESRI point geometry to GeoJSON
    convert_esri_linestring: Convert ESRI paths to GeoJSON LineString
    convert_esri_polygon: Convert ESRI rings to GeoJSON Polygon
    convert_esri_to_geojson: Main dispatcher for ESRI to GeoJSON conversion
    shapely_to_esri_polygon: Convert Shapely Polygon/MultiPolygon to ESRI JSON
    count_geometry_vertices: Count total vertices in a geometry
    simplify_for_query: Simplify geometry for server queries
"""

from typing import Dict, Optional, List
from shapely.geometry import Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry

from prism.log import get_logger

logger = get_logger(__name__)


def convert_esri_point(geom: Dict, props: Dict) -> Optional[Dict]:
    """
    Convert ESRI point geometry to GeoJSON Feature.

    Parameters:
    -----------
    geom : Dict
        ESRI geometry with 'x' and 'y' keys
    props : Dict
        Feature attributes/properties

    Returns:
    --------
    Optional[Dict]
        GeoJSON Feature dict or None if conversion fails

    Example:
        >>> geom = {'x': -73.9857, 'y': 40.7484}
        >>> props = {'name': 'New York'}
        >>> convert_esri_point(geom, props)
        {'type': 'Feature', 'geometry': {...}, 'properties': {...}}
    """
    if not geom or 'x' not in geom or 'y' not in geom:
        return None

    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [geom['x'], geom['y']]
        },
        'properties': props
    }


def convert_esri_linestring(geom: Dict, props: Dict) -> Optional[Dict]:
    """
    Convert ESRI paths geometry to GeoJSON LineString or MultiLineString.

    ESRI represents polylines as arrays of paths, where each path is an array
    of coordinate pairs. Single path becomes LineString, multiple paths become
    MultiLineString.

    Parameters:
    -----------
    geom : Dict
        ESRI geometry with 'paths' key
    props : Dict
        Feature attributes/properties

    Returns:
    --------
    Optional[Dict]
        GeoJSON Feature dict or None if conversion fails
    """
    if not geom or 'paths' not in geom or not geom['paths']:
        return None

    # Single path = LineString, multiple paths = MultiLineString
    if len(geom['paths']) == 1:
        coords = geom['paths'][0]
        geom_type = 'LineString'
    else:
        coords = geom['paths']
        geom_type = 'MultiLineString'

    return {
        'type': 'Feature',
        'geometry': {
            'type': geom_type,
            'coordinates': coords
        },
        'properties': props
    }


def convert_esri_polygon(geom: Dict, props: Dict) -> Optional[Dict]:
    """
    Convert ESRI rings geometry to GeoJSON Polygon.

    ESRI represents polygons as arrays of rings, where each ring is an array
    of coordinate pairs. The first ring is the exterior, subsequent rings are holes.

    Parameters:
    -----------
    geom : Dict
        ESRI geometry with 'rings' key
    props : Dict
        Feature attributes/properties

    Returns:
    --------
    Optional[Dict]
        GeoJSON Feature dict or None if conversion fails
    """
    if not geom or 'rings' not in geom or not geom['rings']:
        return None

    return {
        'type': 'Feature',
        'geometry': {
            'type': 'Polygon',
            'coordinates': geom['rings']
        },
        'properties': props
    }


def convert_esri_to_geojson(esri_feature: Dict) -> Optional[Dict]:
    """
    Main converter dispatcher for ESRI JSON to GeoJSON.

    Detects the geometry type and calls the appropriate conversion function.

    Parameters:
    -----------
    esri_feature : Dict
        ESRI JSON feature with 'geometry' and 'attributes' keys

    Returns:
    --------
    Optional[Dict]
        GeoJSON Feature dict or None if conversion fails

    Example:
        >>> esri_feature = {
        ...     'geometry': {'x': -73.9857, 'y': 40.7484},
        ...     'attributes': {'name': 'New York', 'population': 8000000}
        ... }
        >>> convert_esri_to_geojson(esri_feature)
        {'type': 'Feature', 'geometry': {...}, 'properties': {...}}
    """
    geom = esri_feature.get('geometry')
    props = esri_feature.get('attributes', {})

    if not geom:
        return None

    # Detect geometry type by structure
    if 'x' in geom and 'y' in geom:
        # Point geometry
        return convert_esri_point(geom, props)
    elif 'paths' in geom:
        # LineString/MultiLineString geometry
        return convert_esri_linestring(geom, props)
    elif 'rings' in geom:
        # Polygon geometry
        return convert_esri_polygon(geom, props)

    # Unknown geometry type
    return None


def shapely_to_esri_polygon(geom: BaseGeometry) -> Optional[Dict]:
    """
    Convert Shapely Polygon/MultiPolygon to ESRI JSON polygon format.

    This function converts Shapely geometry objects to the ESRI JSON format
    required for spatial queries to ArcGIS FeatureServers.

    Parameters:
    -----------
    geom : BaseGeometry
        Shapely Polygon or MultiPolygon geometry

    Returns:
    --------
    Optional[Dict]
        ESRI JSON polygon dict with 'rings' and 'spatialReference' keys,
        or None if geometry is invalid/unsupported

    ESRI JSON Format:
        {
            "rings": [[[x1,y1], [x2,y2], ...], [[hole1], ...]],
            "spatialReference": {"wkid": 4326}
        }

    Notes:
    ------
    - All rings (exterior and interior) are combined into a single array
    - For MultiPolygon, rings from all component polygons are combined
    - Coordinates are [x, y] format (longitude, latitude)
    """
    if geom is None or geom.is_empty:
        return None

    rings: List[List[List[float]]] = []

    if geom.geom_type == 'Polygon':
        # Exterior ring
        exterior_coords = list(geom.exterior.coords)
        rings.append([[x, y] for x, y in exterior_coords])

        # Interior rings (holes)
        for interior in geom.interiors:
            interior_coords = list(interior.coords)
            rings.append([[x, y] for x, y in interior_coords])

    elif geom.geom_type == 'MultiPolygon':
        for polygon in geom.geoms:
            # Exterior ring
            exterior_coords = list(polygon.exterior.coords)
            rings.append([[x, y] for x, y in exterior_coords])

            # Interior rings (holes)
            for interior in polygon.interiors:
                interior_coords = list(interior.coords)
                rings.append([[x, y] for x, y in interior_coords])
    else:
        # Unsupported geometry type
        return None

    return {
        'rings': rings,
        'spatialReference': {'wkid': 4326}
    }


def count_geometry_vertices(geom: BaseGeometry) -> int:
    """
    Count total vertices in a Polygon or MultiPolygon geometry.

    Parameters:
    -----------
    geom : BaseGeometry
        Shapely geometry (Polygon or MultiPolygon)

    Returns:
    --------
    int
        Total number of vertices in the geometry
    """
    if geom is None or geom.is_empty:
        return 0

    if geom.geom_type == 'Polygon':
        count = len(geom.exterior.coords)
        for interior in geom.interiors:
            count += len(interior.coords)
        return count

    elif geom.geom_type == 'MultiPolygon':
        total = 0
        for polygon in geom.geoms:
            total += len(polygon.exterior.coords)
            for interior in polygon.interiors:
                total += len(interior.coords)
        return total

    return 0


def calculate_bbox_fill_ratio(geom: BaseGeometry) -> float:
    """
    Calculate how much of the bounding box the polygon fills.

    This ratio helps determine the optimal query strategy:
    - High ratio (>0.5): Polygon fills most of bbox → envelope query is efficient
    - Low ratio (<0.5): Polygon is sparse/discontiguous → polygon query is efficient

    Parameters:
    -----------
    geom : BaseGeometry
        Shapely Polygon or MultiPolygon geometry

    Returns:
    --------
    float
        Ratio of polygon area to bounding box area (0.0 to 1.0)
        Returns 1.0 if calculation fails (defaults to envelope query)
    """
    if geom is None or geom.is_empty:
        return 1.0

    try:
        # Get bounding box area
        minx, miny, maxx, maxy = geom.bounds
        bbox_area = (maxx - minx) * (maxy - miny)

        if bbox_area <= 0:
            return 1.0

        # Get polygon area
        polygon_area = geom.area

        ratio = polygon_area / bbox_area
        return min(ratio, 1.0)  # Cap at 1.0

    except Exception:
        return 1.0  # Default to envelope on error


def calculate_area_sq_miles(geom: BaseGeometry) -> float:
    """
    Estimate area of geometry in square miles.

    Uses a simple lat/lon to sq miles approximation suitable for CONUS.
    Not geodetically precise but sufficient for threshold calculations.

    Parameters:
    -----------
    geom : BaseGeometry
        Shapely geometry in EPSG:4326 (lat/lon)

    Returns:
    --------
    float
        Approximate area in square miles
    """
    if geom is None or geom.is_empty:
        return 0.0

    try:
        # Get centroid latitude for scaling
        centroid = geom.centroid
        lat = centroid.y

        # Approximate degrees to miles at this latitude
        # 1 degree latitude ≈ 69 miles (fairly constant)
        # 1 degree longitude ≈ 69 * cos(lat) miles
        import math
        lat_miles_per_deg = 69.0
        lon_miles_per_deg = 69.0 * math.cos(math.radians(lat))

        # Area in degrees² * conversion factor
        area_deg2 = geom.area
        area_sq_miles = area_deg2 * lat_miles_per_deg * lon_miles_per_deg

        return area_sq_miles

    except Exception:
        return 0.0


def calculate_dynamic_bbox_threshold(area_sq_miles: float) -> float:
    """
    Calculate dynamic bbox fill threshold based on input area size.

    The threshold determines when to use polygon query vs envelope query.
    If bbox_fill_ratio >= threshold → use envelope (polygon is compact enough)
    If bbox_fill_ratio < threshold → use polygon query (too much empty space in bbox)

    Strategy:
    - Small areas: Low threshold (use envelope for most shapes, even squiggly ones)
      Rationale: Small areas won't hit 1000 feature limit, envelope is faster
    - Large areas: High threshold (only use envelope if nearly rectangular)
      Rationale: Large squiggly areas would return too many false positives with envelope

    Parameters:
    -----------
    area_sq_miles : float
        Approximate area of input geometry in square miles

    Returns:
    --------
    float
        Threshold for bbox fill ratio (0.0 to 1.0)
        Higher threshold = need more compact shape to use envelope (prefer polygon query)
        Lower threshold = use envelope for most shapes (prefer envelope query)

    Scale (envelope-friendly for small areas, polygon-friendly for large areas):
        < 100 sq mi:     0.05 (small area, use envelope unless extremely sparse)
        100-500 sq mi:   0.05→0.50 (gradually require more compactness)
        500-1500 sq mi:  0.50→0.70 (medium areas, balanced)
        1500-3000 sq mi: 0.70→0.80 (large areas, need fairly compact for envelope)
        3000-4000 sq mi: 0.80→0.95 (very large, need near-rectangle for envelope)
        > 4000 sq mi:    0.95 (huge areas, only envelope if nearly perfect rectangle)
    """
    if area_sq_miles < 100:
        return 0.05
    elif area_sq_miles < 500:
        # Linear interpolation from 0.05 to 0.50
        return 0.05 + (area_sq_miles - 100) / 400 * 0.45
    elif area_sq_miles < 1500:
        # Linear interpolation from 0.50 to 0.70
        return 0.50 + (area_sq_miles - 500) / 1000 * 0.20
    elif area_sq_miles < 3000:
        # Linear interpolation from 0.70 to 0.80
        return 0.70 + (area_sq_miles - 1500) / 1500 * 0.10
    elif area_sq_miles < 4000:
        # Linear interpolation from 0.80 to 0.95
        return 0.80 + (area_sq_miles - 3000) / 1000 * 0.15
    else:
        # Very large areas: 0.95 (only envelope if nearly perfect rectangle)
        return 0.95


def simplify_for_query(
    geom: BaseGeometry,
    max_vertices: int = 1000,
    tolerance: float = 0.0001,
    max_tolerance: float = 0.01
) -> BaseGeometry:
    """
    Simplify geometry to reduce vertex count for server queries.

    Uses progressive simplification with topology preservation to reduce
    complex geometries to a manageable size for ArcGIS FeatureServer queries.

    Parameters:
    -----------
    geom : BaseGeometry
        Input geometry to simplify
    max_vertices : int
        Maximum vertex count before simplification is applied (default: 1000)
    tolerance : float
        Initial simplification tolerance in degrees (default: 0.0001 ~ 11m)
    max_tolerance : float
        Maximum simplification tolerance to prevent over-simplification
        (default: 0.01 ~ 1.1km)

    Returns:
    --------
    BaseGeometry
        Simplified geometry (or original if already under max_vertices)

    Notes:
    ------
    - Uses progressive simplification: increases tolerance until under limit
    - Preserves topology to avoid self-intersections
    - Maximum tolerance cap prevents severe shape distortion
    - Returns original geometry if simplification would make it invalid
    """
    original_vertex_count = count_geometry_vertices(geom)

    if original_vertex_count <= max_vertices:
        return geom

    logger.debug(
        f"Simplifying geometry: {original_vertex_count} vertices "
        f"exceeds limit of {max_vertices}"
    )

    current_tolerance = tolerance
    simplified = geom

    for i in range(5):  # Max 5 iterations
        simplified = geom.simplify(current_tolerance, preserve_topology=True)
        new_count = count_geometry_vertices(simplified)

        logger.debug(
            f"  Iteration {i+1}: tolerance={current_tolerance:.6f}, "
            f"vertices={new_count}"
        )

        if new_count <= max_vertices:
            break

        current_tolerance *= 2

        if current_tolerance > max_tolerance:
            logger.warning(
                f"Reached max tolerance ({max_tolerance}), "
                f"vertices still at {new_count}"
            )
            break

    final_count = count_geometry_vertices(simplified)

    # Validate simplified geometry
    if simplified.is_empty or not simplified.is_valid:
        logger.warning("Simplified geometry invalid, using original")
        return geom

    if final_count < original_vertex_count:
        logger.info(
            f"Simplified from {original_vertex_count} to {final_count} vertices"
        )

    return simplified
