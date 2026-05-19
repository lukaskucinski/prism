"""
Per-layer ingest pipeline.

For each layer in prism_layers:
  1. Build state-AOI polygon from prism_states (or PRISM_PILOT_STATES env).
  2. Query the ArcGIS service via PEIT's `query_arcgis_layer` (POST, polygon-mode,
     paginated, with envelope fallback).
  3. Convert ESRI JSON → GeoDataFrame (WGS84).
  4. Clip to state AOI.
  5. H3-index features into R8 cells (via h3_indexer).
  6. Write distinct hexes to prism_hex_r8 (polygons) and rows to
     prism_hex_layer (h3_index, layer_id, feature_count).
  7. Update prism_layers.ingest_status / last_ingested / feature_count.
  8. Append a prism_ingest_log row.

Failures are isolated per layer: a single bad service does not abort the run.
Retries with exponential backoff up to 3 attempts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Iterable

import geopandas as gpd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from prism.db import pg_conn, supabase_admin
from prism.index.h3_indexer import cell_polygon_wkt, features_to_r8_cells
from prism.ingest.arcgis_query import query_arcgis_layer
from prism.ingest.geometry_converters import (
    count_geometry_vertices,
    shapely_to_esri_polygon,
    simplify_for_query,
)
from prism.ingest.local_sink import LocalSink
from prism.log import db_log, get_logger

logger = get_logger(__name__)


@dataclass
class LayerRecord:
    layer_id: str
    layer_name: str
    source_url: str
    source_layer_id: int
    geometry_type: str
    friction_category: str
    service_type: str


@dataclass
class IngestResult:
    layer_id: str
    status: str  # 'success' | 'partial' | 'failed' | 'skipped'
    features_processed: int = 0
    hexes_written: int = 0
    error: str | None = None
    duration_ms: int = 0


def fetch_layers(only_layer_ids: list[str] | None = None) -> list[LayerRecord]:
    sb = supabase_admin()
    q = sb.table("prism_layers").select(
        "layer_id, layer_name, source_url, source_layer_id, geometry_type, friction_category, service_type"
    )
    if only_layer_ids:
        q = q.in_("layer_id", only_layer_ids)
    rows = q.execute().data or []
    return [LayerRecord(**r) for r in rows]


def fetch_state_aoi(state_abbrs: Iterable[str]) -> BaseGeometry:
    """Union of prism_states geometries for the given abbreviations.

    Kept for backwards compat — prefer fetch_state_aois (per-state dict) so
    each state can be ingested separately. Combining disjoint states into a
    single AOI forces ArcGIS envelope-mode queries, which return tons of
    features from outside both states.
    """
    return _fetch_union_via_psycopg(list(state_abbrs))


def fetch_state_aois(state_abbrs: Iterable[str]) -> dict[str, BaseGeometry]:
    """Per-state AOI geometries keyed by state_abbr."""
    abbrs = list(state_abbrs)
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state_abbr, ST_AsGeoJSON(geom) FROM prism_states WHERE state_abbr = ANY(%s)",
            (abbrs,),
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError(
            f"No prism_states rows for {abbrs}. Did you run `python -m prism.boundaries.load_tiger`?"
        )
    return {abbr: shape(json.loads(geojson)) for abbr, geojson in rows}


def _fetch_union_via_psycopg(state_abbrs: list[str]) -> BaseGeometry:
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM prism_states WHERE state_abbr = ANY(%s)",
            (state_abbrs,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise RuntimeError(f"No AOI geometry for {state_abbrs}")
        return shape(json.loads(row[0]))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _query_with_retry(
    layer: LayerRecord,
    aoi_gdf: gpd.GeoDataFrame,
    clip_boundary: BaseGeometry,
    esri_polygon_json: str | None = None,
    polygon_query_metadata: dict | None = None,
) -> gpd.GeoDataFrame:
    gdf, meta = query_arcgis_layer(
        layer_url=layer.source_url,
        layer_id=layer.source_layer_id,
        polygon_geom=aoi_gdf,
        layer_name=layer.layer_name,
        geometry_type=layer.geometry_type,
        clip_boundary=clip_boundary,
        esri_polygon_json=esri_polygon_json,
        polygon_query_metadata=polygon_query_metadata,
        pagination_max_iterations=50,   # 50 × 2000 = 100k features per layer-state
        pagination_total_timeout=600.0,  # 10 min per layer-state
    )
    if meta.get("error"):
        raise RuntimeError(f"ArcGIS query failed: {meta['error']}")
    if gdf is None:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gdf


def _build_polygon_query_payload(aoi: BaseGeometry) -> tuple[str | None, dict]:
    """
    Pre-build the ESRI polygon JSON string + metadata for server-side polygon-mode
    queries. Returns (json_str, metadata). Simplifies if the AOI has too many
    vertices for a single POST body.
    """
    raw_vertices = count_geometry_vertices(aoi)
    target = aoi
    simplification_applied = False
    if raw_vertices > 1000:
        target = simplify_for_query(aoi, max_vertices=1000)
        simplification_applied = True
    final_vertices = count_geometry_vertices(target)
    esri = shapely_to_esri_polygon(target)
    if esri is None:
        return None, {"query_vertices": 0}
    return json.dumps(esri), {
        "query_vertices": final_vertices,
        "raw_vertices": raw_vertices,
        "simplification_applied": simplification_applied,
    }


def ingest_layer(
    layer: LayerRecord,
    aoi: BaseGeometry,
    local_sink: "LocalSink | None" = None,
) -> IngestResult:
    """
    Query the layer's ArcGIS service, H3-index the features at R8, and write
    results either to Supabase (default) or to a local GeoPackage if a
    `local_sink` is provided.

    Either way, prism_layers.ingest_status / prism_ingest_log are updated in
    Supabase so we keep a single auditable record of what was attempted.
    """
    start = time.monotonic()
    sink_label = f" → local:{local_sink.path.name}" if local_sink else ""
    logger.info("→ %s (%s)%s", layer.layer_name, layer.geometry_type, sink_label)

    try:
        aoi_gdf = gpd.GeoDataFrame(geometry=[aoi], crs="EPSG:4326")
        esri_json, poly_meta = _build_polygon_query_payload(aoi)
        # `aoi` is the single (possibly multi) geometry; pass directly as
        # clip_boundary so we don't need GeoPandas 1.0's union_all().
        gdf = _query_with_retry(
            layer,
            aoi_gdf,
            aoi,
            esri_polygon_json=esri_json,
            polygon_query_metadata=poly_meta,
        )
    except RetryError as e:
        return _record_failure(layer, f"retries exhausted: {e}", start)
    except Exception as e:  # noqa: BLE001
        return _record_failure(layer, str(e), start)

    if gdf is None or gdf.empty:
        return _record_skip(layer, "no features intersecting AOI", start)

    # Drop empty/invalid geoms
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    if gdf.empty:
        return _record_skip(layer, "all features empty after parse", start)

    feature_count = len(gdf)

    # H3-index
    cell_counts = features_to_r8_cells(
        gdf,
        geometry_type=layer.geometry_type,
        friction_category=layer.friction_category,
    )
    if not cell_counts:
        return _record_skip(layer, "no R8 cells emitted", start)

    # Write to DB (or to the local GeoPackage if a sink was provided)
    if local_sink is not None:
        hexes_written = local_sink.add_layer_hits(
            layer_id=layer.layer_id,
            layer_name=layer.layer_name,
            friction_category=layer.friction_category,
            cell_counts=cell_counts,
        )
    else:
        hexes_written = _write_hexes(layer.layer_id, cell_counts)

    duration_ms = int((time.monotonic() - start) * 1000)
    _update_layer_status(
        layer.layer_id,
        status="success",
        feature_count=feature_count,
        error=None,
    )
    db_log(
        layer_id=layer.layer_id,
        action="h3_index",
        status="ok",
        duration_ms=duration_ms,
        features_processed=feature_count,
        hexes_written=hexes_written,
        message=f"{layer.layer_name}: {feature_count} features → {hexes_written} hexes",
    )
    return IngestResult(
        layer_id=layer.layer_id,
        status="success",
        features_processed=feature_count,
        hexes_written=hexes_written,
        duration_ms=duration_ms,
    )


def _write_hexes(layer_id: str, cell_counts: list[tuple[str, int]]) -> int:
    """
    Upsert hex polygons into prism_hex_r8 (geom + h3_index only; scoring runs
    in a separate pass). Upsert (h3_index, layer_id, feature_count) into
    prism_hex_layer.
    """
    if not cell_counts:
        return 0
    with pg_conn() as conn, conn.cursor() as cur:
        # Upsert hex polygons
        hex_rows = [(c, cell_polygon_wkt(c)) for c, _ in cell_counts]
        cur.executemany(
            """
            INSERT INTO prism_hex_r8 (h3_index, geom)
            VALUES (%s, ST_GeomFromText(%s, 4326))
            ON CONFLICT (h3_index) DO NOTHING
            """,
            hex_rows,
        )
        # Upsert join rows
        join_rows = [(c, layer_id, n) for c, n in cell_counts]
        cur.executemany(
            """
            INSERT INTO prism_hex_layer (h3_index, layer_id, feature_count)
            VALUES (%s, %s, %s)
            ON CONFLICT (h3_index, layer_id) DO UPDATE
              SET feature_count = EXCLUDED.feature_count
            """,
            join_rows,
        )
        conn.commit()
    return len(cell_counts)


def _update_layer_status(
    layer_id: str,
    *,
    status: str,
    feature_count: int | None = None,
    error: str | None = None,
) -> None:
    sb = supabase_admin()
    update: dict = {
        "ingest_status": status,
        "last_ingested": "now()",
        "last_ingest_error": error,
    }
    if feature_count is not None:
        update["feature_count"] = feature_count
    # supabase-py won't interpolate `now()`; use raw RPC via psycopg
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE prism_layers
               SET ingest_status = %s,
                   last_ingested = now(),
                   last_ingest_error = %s,
                   feature_count = COALESCE(%s, feature_count),
                   updated_at = now()
             WHERE layer_id = %s
            """,
            (status, error, feature_count, layer_id),
        )
        conn.commit()


def _record_failure(layer: LayerRecord, error: str, start: float) -> IngestResult:
    duration_ms = int((time.monotonic() - start) * 1000)
    _update_layer_status(layer.layer_id, status="failed", error=error)
    db_log(
        layer_id=layer.layer_id,
        action="error",
        status="fail",
        duration_ms=duration_ms,
        message=f"{layer.layer_name}: {error}",
    )
    logger.warning("✗ %s failed: %s", layer.layer_name, error)
    return IngestResult(
        layer_id=layer.layer_id,
        status="failed",
        error=error,
        duration_ms=duration_ms,
    )


def _record_skip(layer: LayerRecord, reason: str, start: float) -> IngestResult:
    duration_ms = int((time.monotonic() - start) * 1000)
    _update_layer_status(layer.layer_id, status="skipped", error=reason, feature_count=0)
    db_log(
        layer_id=layer.layer_id,
        action="h3_index",
        status="skip",
        duration_ms=duration_ms,
        message=f"{layer.layer_name}: {reason}",
    )
    logger.info("○ %s skipped: %s", layer.layer_name, reason)
    return IngestResult(
        layer_id=layer.layer_id,
        status="skipped",
        error=reason,
        duration_ms=duration_ms,
    )
