-- Sparse hex storage at three resolutions. Only hexes with >=1 layer
-- intersection are written. R8 is the base; R7 and R6 are aggregates.

CREATE TABLE prism_hex_r8 (
  h3_index             TEXT PRIMARY KEY,
  friction_score       REAL DEFAULT 0,
  layer_count          INTEGER DEFAULT 0,
  top_friction_driver  TEXT,
  category_flags       JSONB DEFAULT '{}'::jsonb,
  geom                 geometry(Polygon, 4326) NOT NULL,
  user_id              UUID, -- Phase 6: paid-feature attribution; NULL in v1
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_hex_r8_geom_idx   ON prism_hex_r8 USING GIST (geom);
CREATE INDEX prism_hex_r8_score_idx  ON prism_hex_r8 (friction_score);
CREATE INDEX prism_hex_r8_flags_idx  ON prism_hex_r8 USING GIN (category_flags);

CREATE TABLE prism_hex_r7 (
  h3_index             TEXT PRIMARY KEY,
  friction_score       REAL DEFAULT 0,
  layer_count          INTEGER DEFAULT 0,
  top_friction_driver  TEXT,
  category_flags       JSONB DEFAULT '{}'::jsonb,
  geom                 geometry(Polygon, 4326) NOT NULL,
  user_id              UUID,
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_hex_r7_geom_idx   ON prism_hex_r7 USING GIST (geom);
CREATE INDEX prism_hex_r7_score_idx  ON prism_hex_r7 (friction_score);
CREATE INDEX prism_hex_r7_flags_idx  ON prism_hex_r7 USING GIN (category_flags);

CREATE TABLE prism_hex_r6 (
  h3_index             TEXT PRIMARY KEY,
  friction_score       REAL DEFAULT 0,
  layer_count          INTEGER DEFAULT 0,
  top_friction_driver  TEXT,
  category_flags       JSONB DEFAULT '{}'::jsonb,
  geom                 geometry(Polygon, 4326) NOT NULL,
  user_id              UUID,
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_hex_r6_geom_idx   ON prism_hex_r6 USING GIST (geom);
CREATE INDEX prism_hex_r6_score_idx  ON prism_hex_r6 (friction_score);
CREATE INDEX prism_hex_r6_flags_idx  ON prism_hex_r6 USING GIN (category_flags);

ALTER TABLE prism_hex_r8 ENABLE ROW LEVEL SECURITY;
ALTER TABLE prism_hex_r7 ENABLE ROW LEVEL SECURITY;
ALTER TABLE prism_hex_r6 ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE prism_hex_r8 IS 'Base resolution; one row per intersecting hex';
COMMENT ON TABLE prism_hex_r7 IS 'z 7-9 tile reads; aggregated from R8';
COMMENT ON TABLE prism_hex_r6 IS 'z <= 6 tile reads; aggregated from R7';
