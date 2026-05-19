-- PRISM extensions
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;

-- Note: h3 indexing happens in Python (h3 package), not in Postgres.
-- Hex polygons are pre-computed and stored as geometry columns.

COMMENT ON EXTENSION postgis IS 'Spatial types and indexes for PRISM hex grid + boundaries';
