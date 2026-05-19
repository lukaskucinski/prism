"""
ArcGIS FeatureServer query module for PEIT Map Creator.

This module handles querying ArcGIS FeatureServers with spatial intersection
and converting the results to GeoDataFrames. Uses POST requests to avoid URI length
limitations and performs client-side filtering for precise polygon intersection.

Supports two query strategies:
1. Polygon query: Sends actual polygon geometry for precise server-side filtering
2. Envelope query: Sends bounding box (fallback for complex geometries or errors)

Supports pagination for retrieving features beyond server limits (1000-2000 typical).

Functions:
    fetch_layer_metadata: Get layer metadata including pagination support
    paginated_query: Execute paginated query to fetch all features
    query_arcgis_layer: Query a FeatureServer layer and return intersecting features
"""

import geopandas as gpd
import requests
import json
import time
from typing import Tuple, Optional, Dict, List
from shapely.geometry.base import BaseGeometry
from prism.ingest.geometry_converters import convert_esri_to_geojson
from prism.log import get_logger
from prism.ingest.clipping import clip_geodataframe

logger = get_logger(__name__)


def fetch_layer_metadata(
    layer_url: str,
    layer_id: int,
    timeout: int = 30
) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Fetch layer metadata to determine pagination support and ObjectID field.

    Queries the layer's metadata endpoint to extract information needed for
    pagination, including whether the layer supports it and the ObjectID field name.

    Parameters:
    -----------
    layer_url : str
        Base URL of the FeatureServer
    layer_id : int
        Layer index within the FeatureServer
    timeout : int
        Request timeout in seconds (default: 30)

    Returns:
    --------
    Tuple[Optional[Dict], Optional[str]]
        - metadata dict with keys:
          - supports_pagination: bool
          - max_record_count: int
          - oid_field: str (name of ObjectID field)
        - error message if failed, None if successful
    """
    metadata_url = f"{layer_url}/{layer_id}?f=json"

    try:
        response = requests.get(metadata_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        # Check for error in response
        if 'error' in data:
            error_msg = data['error'].get('message', 'Unknown error')
            return None, f"Layer metadata error: {error_msg}"

        # Extract pagination support
        advanced_caps = data.get('advancedQueryCapabilities', {})
        supports_pagination = advanced_caps.get('supportsPagination', False)

        # Extract max record count
        max_record_count = data.get('maxRecordCount', 1000)

        # Find ObjectID field (look for esriFieldTypeOID type)
        oid_field = None
        fields = data.get('fields', [])
        for field in fields:
            if field.get('type') == 'esriFieldTypeOID':
                oid_field = field.get('name')
                break

        # Fallback: try common ObjectID field names
        if not oid_field:
            common_oid_names = ['OBJECTID', 'FID', 'OID', 'objectid', 'fid', 'oid']
            field_names = [f.get('name', '') for f in fields]
            for common_name in common_oid_names:
                if common_name in field_names:
                    oid_field = common_name
                    break

        return {
            'supports_pagination': supports_pagination,
            'max_record_count': max_record_count,
            'oid_field': oid_field
        }, None

    except requests.exceptions.Timeout:
        return None, "Metadata request timed out"
    except requests.exceptions.RequestException as e:
        return None, f"Metadata request failed: {str(e)}"
    except Exception as e:
        return None, f"Metadata parsing error: {str(e)}"


def paginated_query(
    query_url: str,
    base_params: Dict,
    oid_field: str,
    max_record_count: int,
    layer_name: str,
    max_iterations: int = 10,
    total_timeout: float = 300.0,
    request_timeout: int = 60
) -> Tuple[List[Dict], Dict]:
    """
    Execute paginated query to fetch all features beyond server limit.

    Uses resultOffset and resultRecordCount parameters to paginate through
    all available features. Requires orderByFields for consistent ordering.

    Parameters:
    -----------
    query_url : str
        Full query URL endpoint
    base_params : Dict
        Base query parameters (geometry, spatial rel, etc.)
    oid_field : str
        Name of ObjectID field for ordering
    max_record_count : int
        Maximum records per request (from layer metadata)
    layer_name : str
        Name of the layer for logging
    max_iterations : int
        Safety limit on number of pagination iterations (default: 10)
    total_timeout : float
        Maximum total time for all pagination requests (default: 300 seconds)
    request_timeout : int
        Timeout per individual request (default: 60 seconds)

    Returns:
    --------
    Tuple[List[Dict], Dict]
        - List of all ESRI JSON features
        - Pagination metadata dict with keys:
          - pages_fetched: int
          - total_features_fetched: int
          - exceeded_limit_final: bool (still more features available)
          - stopped_reason: str | None ('max_iterations' | 'timeout' | None)
          - pagination_time: float
    """
    all_features = []
    pagination_metadata = {
        'pages_fetched': 0,
        'total_features_fetched': 0,
        'exceeded_limit_final': False,
        'stopped_reason': None,
        'pagination_time': 0.0
    }

    start_time = time.time()
    offset = 0
    iteration = 0
    result = {}  # Initialize to empty dict to avoid NameError if loop never executes

    while iteration < max_iterations:
        # Check total timeout
        elapsed = time.time() - start_time
        if elapsed >= total_timeout:
            pagination_metadata['stopped_reason'] = 'timeout'
            logger.warning(
                f"    ⚠ Pagination timeout after {iteration} pages "
                f"({elapsed:.1f}s >= {total_timeout}s limit)"
            )
            break

        # Build paginated query parameters
        paginated_params = base_params.copy()
        paginated_params['resultOffset'] = offset
        paginated_params['resultRecordCount'] = max_record_count
        paginated_params['orderByFields'] = oid_field

        try:
            response = requests.post(query_url, data=paginated_params, timeout=request_timeout)
            response.raise_for_status()
            result = response.json()

            # Check for error in response
            if 'error' in result:
                error_msg = result['error'].get('message', 'Unknown error')
                logger.warning(f"    ⚠ Pagination error on page {iteration + 1}: {error_msg}")
                pagination_metadata['stopped_reason'] = f'error: {error_msg}'
                break

            # Extract features from this page
            page_features = result.get('features', [])
            page_count = len(page_features)
            all_features.extend(page_features)

            iteration += 1
            pagination_metadata['pages_fetched'] = iteration

            # Check if more results available
            exceeded_limit = result.get('exceededTransferLimit', False)

            if exceeded_limit:
                logger.info(f"    - Page {iteration}: {page_count} features (more available)")
                offset += max_record_count
            else:
                logger.info(f"    - Page {iteration}: {page_count} features (complete)")
                break

        except requests.exceptions.Timeout:
            logger.warning(f"    ⚠ Request timeout on page {iteration + 1}")
            pagination_metadata['stopped_reason'] = 'request_timeout'
            break
        except requests.exceptions.RequestException as e:
            logger.warning(f"    ⚠ Request error on page {iteration + 1}: {e}")
            pagination_metadata['stopped_reason'] = f'request_error: {str(e)}'
            break

    # Check if we hit max iterations
    if iteration >= max_iterations and result.get('exceededTransferLimit', False):
        pagination_metadata['stopped_reason'] = 'max_iterations'
        pagination_metadata['exceeded_limit_final'] = True
        logger.warning(
            f"    ⚠ Maximum pagination limit ({max_iterations} pages) reached. "
            f"Additional features may exist."
        )

    pagination_metadata['total_features_fetched'] = len(all_features)
    pagination_metadata['pagination_time'] = time.time() - start_time

    return all_features, pagination_metadata


def query_arcgis_layer(
    layer_url: str,
    layer_id: int,
    polygon_geom: gpd.GeoDataFrame,
    layer_name: str = "Layer",
    clip_boundary: Optional[BaseGeometry] = None,
    geometry_type: Optional[str] = None,
    use_polygon_query: bool = True,
    esri_polygon_json: Optional[str] = None,
    polygon_query_metadata: Optional[Dict] = None,
    pagination_enabled: bool = True,
    pagination_max_iterations: int = 10,
    pagination_total_timeout: float = 300.0
) -> Tuple[Optional[gpd.GeoDataFrame], Dict]:
    """
    Query an ArcGIS FeatureServer with spatial intersection.

    Supports two query strategies:
    1. Polygon query (default): Sends actual polygon geometry for precise
       server-side filtering. More efficient for complex/discontiguous polygons.
    2. Envelope query (fallback): Sends bounding box. Used when polygon query
       fails or is disabled.

    Supports pagination to retrieve all features when server limit is exceeded.

    After server-side filtering, applies:
    - Client-side precise polygon intersection filter
    - Client-side geometry clipping (lines/polygons only)

    Parameters:
    -----------
    layer_url : str
        Base URL of the FeatureServer
    layer_id : int
        Layer index within the FeatureServer
    polygon_geom : gpd.GeoDataFrame
        Input polygon for spatial intersection
    layer_name : str
        Name of the layer for logging
    clip_boundary : BaseGeometry, optional
        Geometry boundary to clip results to (typically 1-mile buffer around input)
    geometry_type : str, optional
        Type of geometry ('point', 'line', or 'polygon') for clipping decision
    use_polygon_query : bool
        If True, send actual polygon geometry instead of bounding box (default: True)
    esri_polygon_json : str, optional
        Pre-computed ESRI JSON polygon string for query (avoids per-layer conversion)
    polygon_query_metadata : Dict, optional
        Pre-computed metadata about the polygon query (vertices, simplification info)
    pagination_enabled : bool
        If True, automatically paginate when server limit exceeded (default: True)
    pagination_max_iterations : int
        Maximum number of pagination pages to fetch (default: 10)
    pagination_total_timeout : float
        Maximum total time in seconds for all pagination requests (default: 300)

    Returns:
    --------
    Tuple[Optional[gpd.GeoDataFrame], Dict]
        GeoDataFrame of intersecting features and metadata dictionary

    Metadata Keys:
        - layer_name: Name of the layer
        - feature_count: Final count after filtering
        - server_count: Initial count from server query
        - filtered_count: Number of features filtered out by client-side intersection
        - query_method: 'polygon' | 'envelope' | 'envelope_fallback'
        - query_vertices: Vertex count used in polygon query (if applicable)
        - simplification_applied: Whether geometry was simplified (if applicable)
        - query_fallback_reason: Reason for fallback to envelope (if applicable)
        - clipping: Clipping statistics (if clipping was applied)
        - pagination: Pagination statistics (if pagination was used)
        - results_incomplete: True if results may be incomplete due to limits
        - incomplete_reason: Reason results are incomplete (if applicable)
        - query_time: Total query time in seconds
        - warning: Any warnings (e.g., exceededTransferLimit)
        - error: Error message if query failed
    """
    logger.info(f"  Querying {layer_name}...")

    metadata = {
        'layer_name': layer_name,
        'feature_count': 0,
        'warning': None,
        'error': None,
        'query_time': 0,
        'query_method': 'envelope'  # Default, updated if polygon query succeeds
    }

    start_time = time.time()

    try:
        # Construct query URL
        query_url = f"{layer_url}/{layer_id}/query"

        # Extract polygon geometry for queries
        polygon_geometry = polygon_geom.geometry.iloc[0]

        # Determine query strategy
        query_method = 'envelope'
        result = None

        if use_polygon_query and esri_polygon_json:
            try:
                # Use pre-computed metadata if available
                if polygon_query_metadata:
                    metadata['query_vertices'] = polygon_query_metadata.get('query_vertices')
                    metadata['simplification_applied'] = polygon_query_metadata.get('simplification_applied', False)
                    if metadata['simplification_applied']:
                        metadata['original_vertices'] = polygon_query_metadata.get('original_vertices')

                # Build polygon query parameters using pre-computed ESRI JSON
                params = {
                    'where': '1=1',
                    'geometry': esri_polygon_json,
                    'geometryType': 'esriGeometryPolygon',
                    'spatialRel': 'esriSpatialRelIntersects',
                    'outFields': '*',
                    'returnGeometry': 'true',
                    'f': 'json',
                    'inSR': '4326',
                    'outSR': '4326'
                }

                query_vertices = metadata.get('query_vertices', 'N/A')
                logger.info(f"    - Using polygon query ({query_vertices} vertices)")
                logger.debug(f"Querying: {query_url}")
                response = requests.post(query_url, data=params, timeout=60)
                response.raise_for_status()

                result = response.json()

                # Check for ESRI error in response
                if 'error' in result:
                    error_msg = result['error'].get('message', 'Unknown error')
                    logger.warning(
                        f"    - Polygon query returned ESRI error: {error_msg}, "
                        f"falling back to envelope"
                    )
                    metadata['query_fallback_reason'] = f"esri_error: {error_msg}"
                    result = None
                else:
                    query_method = 'polygon'

            except requests.exceptions.Timeout:
                logger.warning(
                    "    - Polygon query timed out, falling back to envelope"
                )
                metadata['query_fallback_reason'] = "timeout"
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"    - Polygon query failed ({e}), falling back to envelope"
                )
                metadata['query_fallback_reason'] = f"request_error: {str(e)}"
            except Exception as e:
                logger.warning(
                    f"    - Polygon query error ({e}), falling back to envelope"
                )
                metadata['query_fallback_reason'] = f"error: {str(e)}"

        # Fallback to envelope query if polygon query failed or is disabled
        if result is None:
            # Get bounding box (envelope) for spatial query
            bounds = polygon_geom.total_bounds
            envelope = {
                'xmin': bounds[0],
                'ymin': bounds[1],
                'xmax': bounds[2],
                'ymax': bounds[3],
                'spatialReference': {'wkid': 4326}
            }

            # Build envelope query parameters
            params = {
                'where': '1=1',
                'geometry': json.dumps(envelope),
                'geometryType': 'esriGeometryEnvelope',
                'spatialRel': 'esriSpatialRelIntersects',
                'outFields': '*',
                'returnGeometry': 'true',
                'f': 'json',
                'inSR': '4326',
                'outSR': '4326'
            }

            if use_polygon_query:
                # This is a fallback from polygon query
                query_method = 'envelope_fallback'
                logger.info("    - Using envelope query (fallback)")
            else:
                logger.info("    - Using envelope query")

            logger.debug(f"Querying: {query_url}")
            response = requests.post(query_url, data=params, timeout=60)
            response.raise_for_status()
            result = response.json()

        metadata['query_method'] = query_method

        # Check for features
        if 'features' in result and len(result['features']) > 0:
            all_esri_features = result['features']
            first_page_count = len(all_esri_features)
            exceeded_limit = result.get('exceededTransferLimit', False)

            # Handle pagination if limit exceeded and pagination is enabled
            if exceeded_limit and pagination_enabled:
                # Fetch layer metadata to check pagination support
                layer_meta, meta_error = fetch_layer_metadata(layer_url, layer_id)

                if meta_error:
                    logger.warning(f"    ⚠ Could not fetch layer metadata: {meta_error}")
                    logger.warning("    ⚠ Falling back to first page only")

                if layer_meta and layer_meta.get('supports_pagination'):
                    oid_field = layer_meta.get('oid_field')
                    max_record_count = layer_meta.get('max_record_count', 1000)

                    if oid_field:
                        logger.info(f"    - Pagination enabled (OID field: {oid_field})")

                        # Execute full paginated query from the start with consistent ordering
                        all_paginated_features, pagination_meta = paginated_query(
                            query_url=query_url,
                            base_params=params,
                            oid_field=oid_field,
                            max_record_count=max_record_count,
                            layer_name=layer_name,
                            max_iterations=pagination_max_iterations,
                            total_timeout=pagination_total_timeout,
                            request_timeout=60
                        )

                        all_esri_features = all_paginated_features
                        exceeded_limit = pagination_meta.get('exceeded_limit_final', False)

                        # Store pagination metadata
                        metadata['pagination'] = {
                            'used': True,
                            'supports_pagination': True,
                            'oid_field': oid_field,
                            'max_record_count': max_record_count,
                            'pages_fetched': pagination_meta['pages_fetched'],
                            'stopped_reason': pagination_meta.get('stopped_reason')
                        }

                        # Check if results are incomplete
                        if pagination_meta.get('stopped_reason') or exceeded_limit:
                            metadata['results_incomplete'] = True
                            metadata['incomplete_reason'] = pagination_meta.get('stopped_reason') or 'exceeded_limit'
                            logger.warning("    ⚠ WARNING: Results may be INCOMPLETE for this layer")
                            if pagination_meta.get('stopped_reason') == 'max_iterations':
                                logger.warning(
                                    f"    ⚠ Maximum pagination limit ({pagination_max_iterations} pages) reached"
                                )
                            logger.warning("    ⚠ Additional features may exist but could not be retrieved")

                        logger.info(
                            f"    - Server returned {len(all_esri_features)} features "
                            f"({pagination_meta['pages_fetched']} pages)"
                        )
                    else:
                        # No OID field found - can't paginate
                        logger.warning("    ⚠ WARNING: Results may be INCOMPLETE for this layer")
                        logger.warning(
                            f"    ⚠ Server limit: {first_page_count} features reached, "
                            f"no ObjectID field found for pagination"
                        )
                        logger.warning("    ⚠ Additional features may exist but could not be retrieved")
                        metadata['results_incomplete'] = True
                        metadata['incomplete_reason'] = 'no_oid_field'
                        metadata['pagination'] = {
                            'used': False,
                            'supports_pagination': True,
                            'reason': 'no_oid_field'
                        }
                else:
                    # Layer doesn't support pagination
                    logger.warning("    ⚠ WARNING: Results may be INCOMPLETE for this layer")
                    logger.warning(
                        f"    ⚠ Server limit: {first_page_count} features reached, "
                        f"pagination not supported"
                    )
                    logger.warning("    ⚠ Additional features may exist but could not be retrieved")
                    metadata['results_incomplete'] = True
                    metadata['incomplete_reason'] = 'pagination_not_supported'
                    metadata['pagination'] = {
                        'used': False,
                        'supports_pagination': False
                    }

            elif exceeded_limit and not pagination_enabled:
                # Pagination disabled by config
                logger.warning("    ⚠ WARNING: Results may be INCOMPLETE for this layer")
                logger.warning(
                    f"    ⚠ Server limit: {first_page_count} features reached, "
                    f"pagination disabled in config"
                )
                logger.warning("    ⚠ Additional features may exist but could not be retrieved")
                metadata['results_incomplete'] = True
                metadata['incomplete_reason'] = 'pagination_disabled'
                metadata['warning'] = f"Result exceeded server limit. Showing first {first_page_count} features."
            elif not exceeded_limit:
                logger.info(f"    - Server returned {first_page_count} features")

            # Convert ESRI JSON to GeoDataFrame
            features = []
            for feature in all_esri_features:
                geojson_feat = convert_esri_to_geojson(feature)
                if geojson_feat:
                    features.append(geojson_feat)

            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame.from_features(features, crs='EPSG:4326')
            initial_count = len(gdf)

            # Client-side filtering: precise polygon intersection
            # This filters out features that are in the query area but not in the actual polygon
            # (More relevant for envelope queries, but also catches edge cases for polygon queries)
            gdf = gdf[gdf.intersects(polygon_geometry)]

            metadata['server_count'] = initial_count
            metadata['filtered_count'] = initial_count - len(gdf)

            if initial_count != len(gdf):
                logger.info(
                    f"    - Filtered to {len(gdf)} features "
                    f"(removed {initial_count - len(gdf)} outside polygon)"
                )

            # Client-side clipping: clip geometries to buffer boundary
            # Only applies to line and polygon geometries (points cannot extend beyond boundaries)
            if clip_boundary is not None and geometry_type in ('line', 'polygon') and len(gdf) > 0:
                gdf, clip_metadata = clip_geodataframe(
                    gdf, clip_boundary, layer_name, geometry_type
                )
                metadata['clipping'] = clip_metadata

            metadata['feature_count'] = len(gdf)
            logger.info(f"    ✓ Found {len(gdf)} intersecting features")

            metadata['query_time'] = time.time() - start_time
            return gdf, metadata
        else:
            logger.info("    - No intersecting features found")
            metadata['query_time'] = time.time() - start_time
            return None, metadata

    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        logger.error(f"    ✗ {error_msg}")
        metadata['error'] = error_msg
        metadata['query_time'] = time.time() - start_time
        return None, metadata

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"    ✗ {error_msg}", exc_info=True)
        metadata['error'] = error_msg
        metadata['query_time'] = time.time() - start_time
        return None, metadata
