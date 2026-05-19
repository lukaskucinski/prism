-- prism_get_hex_mvt(z, x, y, filter_json)
--
-- Returns a Mapbox Vector Tile (single 'hex' layer) of the appropriate H3
-- resolution table for the given zoom. Applies filters from filter_json:
--   { s: ["VT","NV"], c: ["50007"], d: ["50-1"], r: [0,100],
--     g: ["critical_habitat","floodplain_wetland"] }
--
-- Properties emitted per feature:
--   h3_index, friction_score, layer_count, top_friction_driver

CREATE OR REPLACE FUNCTION prism_get_hex_mvt(
  z          INTEGER,
  x          INTEGER,
  y          INTEGER,
  filter_json JSONB DEFAULT '{}'::jsonb
) RETURNS BYTEA
LANGUAGE plpgsql STABLE PARALLEL SAFE
AS $$
DECLARE
  res_table   TEXT;
  tile_bbox   geometry;
  result      BYTEA;
  sql         TEXT;
  has_states  BOOLEAN := filter_json ? 's' AND jsonb_array_length(filter_json->'s') > 0;
  has_counties BOOLEAN := filter_json ? 'c' AND jsonb_array_length(filter_json->'c') > 0;
  has_districts BOOLEAN := filter_json ? 'd' AND jsonb_array_length(filter_json->'d') > 0;
  has_score   BOOLEAN := filter_json ? 'r';
  has_cats    BOOLEAN := filter_json ? 'g' AND jsonb_array_length(filter_json->'g') > 0;
  score_lo    REAL := 0;
  score_hi    REAL := 100;
BEGIN
  IF z <= 6 THEN
    res_table := 'prism_hex_r6';
  ELSIF z <= 9 THEN
    res_table := 'prism_hex_r7';
  ELSE
    res_table := 'prism_hex_r8';
  END IF;

  tile_bbox := ST_TileEnvelope(z, x, y);

  IF has_score THEN
    score_lo := COALESCE((filter_json->'r'->>0)::real, 0);
    score_hi := COALESCE((filter_json->'r'->>1)::real, 100);
  END IF;

  sql := format($f$
    WITH src AS (
      SELECT
        h3_index,
        friction_score,
        layer_count,
        top_friction_driver,
        ST_AsMVTGeom(
          ST_Transform(geom, 3857),
          ST_TileEnvelope(%s, %s, %s),
          4096, 64, true
        ) AS geom
      FROM %I h
      WHERE h.geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)
        AND h.friction_score BETWEEN %s AND %s
    $f$, z, x, y, res_table, z, x, y, score_lo, score_hi);

  IF has_states THEN
    sql := sql || format($f$
        AND EXISTS (
          SELECT 1 FROM prism_states s
          WHERE s.state_abbr = ANY (
            SELECT jsonb_array_elements_text(%L::jsonb->'s')
          )
          AND ST_Intersects(h.geom, s.geom)
        )
    $f$, filter_json);
  END IF;

  IF has_counties THEN
    sql := sql || format($f$
        AND EXISTS (
          SELECT 1 FROM prism_counties c
          WHERE c.county_fips = ANY (
            SELECT jsonb_array_elements_text(%L::jsonb->'c')
          )
          AND ST_Intersects(h.geom, c.geom)
        )
    $f$, filter_json);
  END IF;

  IF has_districts THEN
    sql := sql || format($f$
        AND EXISTS (
          SELECT 1 FROM prism_districts d
          WHERE d.district_id = ANY (
            SELECT jsonb_array_elements_text(%L::jsonb->'d')
          )
          AND ST_Intersects(h.geom, d.geom)
        )
    $f$, filter_json);
  END IF;

  IF has_cats THEN
    sql := sql || format($f$
        AND (
          SELECT bool_or((h.category_flags ->> cat)::boolean)
          FROM jsonb_array_elements_text(%L::jsonb->'g') AS cat
        )
    $f$, filter_json);
  END IF;

  sql := sql || $f$
    )
    SELECT ST_AsMVT(src, 'hex', 4096, 'geom') FROM src WHERE geom IS NOT NULL;
  $f$;

  EXECUTE sql INTO result;
  RETURN COALESCE(result, ''::bytea);
END;
$$;

REVOKE ALL ON FUNCTION prism_get_hex_mvt(INTEGER, INTEGER, INTEGER, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION prism_get_hex_mvt(INTEGER, INTEGER, INTEGER, JSONB) TO service_role;
