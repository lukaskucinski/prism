-- Catalog of environmental / permitting layers ingested into PRISM.
-- Seeded from APPEIT's layer_config_from_rest_noraw.json (205 layers).

CREATE TABLE prism_layers (
  layer_id           TEXT PRIMARY KEY,
  layer_name         TEXT NOT NULL,
  raw_group          TEXT,
  friction_category  TEXT NOT NULL,
  source_url         TEXT NOT NULL,
  source_layer_id    INTEGER,
  service_type       TEXT NOT NULL CHECK (service_type IN ('FeatureServer','MapServer')),
  geometry_type      TEXT NOT NULL CHECK (geometry_type IN ('polygon','point','line')),
  feature_count      INTEGER DEFAULT 0,
  friction_weight    REAL    DEFAULT 0,
  friction_tier      TEXT    CHECK (friction_tier IN ('high','medium','low')),
  agency_name        TEXT,
  agency_url         TEXT,
  permit_start_url   TEXT,
  ingest_status      TEXT    DEFAULT 'pending'
                     CHECK (ingest_status IN ('pending','success','partial','failed','skipped')),
  last_ingest_error  TEXT,
  last_ingested      TIMESTAMPTZ,
  description        TEXT,
  created_at         TIMESTAMPTZ DEFAULT now(),
  updated_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX prism_layers_category_idx ON prism_layers (friction_category);
CREATE INDEX prism_layers_status_idx   ON prism_layers (ingest_status);

ALTER TABLE prism_layers ENABLE ROW LEVEL SECURITY;
-- v1 has no public read policy; service-role API routes bypass RLS.

COMMENT ON TABLE prism_layers IS '205 APPEIT layers with friction weights, ingest status, and permit links';
