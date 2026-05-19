-- TIGER 2024 boundary tables for geographic filtering.
-- Populated once by `python -m prism.boundaries.load_tiger`.

CREATE TABLE prism_states (
  state_fips  TEXT PRIMARY KEY,    -- 2-digit
  state_name  TEXT NOT NULL,
  state_abbr  TEXT NOT NULL UNIQUE,
  geom        geometry(MultiPolygon, 4326) NOT NULL,
  area_sq_km  REAL,
  created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_states_geom_idx ON prism_states USING GIST (geom);
CREATE INDEX prism_states_abbr_idx ON prism_states (state_abbr);

CREATE TABLE prism_counties (
  county_fips  TEXT PRIMARY KEY,   -- 5-digit (state + county)
  state_fips   TEXT NOT NULL REFERENCES prism_states(state_fips) ON DELETE CASCADE,
  county_name  TEXT NOT NULL,
  geom         geometry(MultiPolygon, 4326) NOT NULL,
  area_sq_km   REAL,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_counties_geom_idx  ON prism_counties USING GIST (geom);
CREATE INDEX prism_counties_state_idx ON prism_counties (state_fips);

CREATE TABLE prism_districts (
  district_id      TEXT PRIMARY KEY,  -- state_fips || '-' || district_number
  state_fips       TEXT NOT NULL REFERENCES prism_states(state_fips) ON DELETE CASCADE,
  district_number  TEXT NOT NULL,
  congress         INTEGER NOT NULL DEFAULT 119,
  geom             geometry(MultiPolygon, 4326) NOT NULL,
  area_sq_km       REAL,
  created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX prism_districts_geom_idx  ON prism_districts USING GIST (geom);
CREATE INDEX prism_districts_state_idx ON prism_districts (state_fips);

ALTER TABLE prism_states    ENABLE ROW LEVEL SECURITY;
ALTER TABLE prism_counties  ENABLE ROW LEVEL SECURITY;
ALTER TABLE prism_districts ENABLE ROW LEVEL SECURITY;

-- Public-readable boundaries (no sensitive data)
CREATE POLICY prism_states_read    ON prism_states    FOR SELECT USING (true);
CREATE POLICY prism_counties_read  ON prism_counties  FOR SELECT USING (true);
CREATE POLICY prism_districts_read ON prism_districts FOR SELECT USING (true);
