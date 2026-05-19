-- Source-of-truth join table: which layers intersect each R8 hex.
-- The denormalized columns on prism_hex_r8 (layer_count, top_friction_driver,
-- category_flags, friction_score) are derived from this table by the scorer.

CREATE TABLE prism_hex_layer (
  h3_index       TEXT NOT NULL,
  layer_id       TEXT NOT NULL REFERENCES prism_layers(layer_id) ON DELETE CASCADE,
  feature_count  INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (h3_index, layer_id)
);
CREATE INDEX prism_hex_layer_layer_idx ON prism_hex_layer (layer_id);
CREATE INDEX prism_hex_layer_h3_idx    ON prism_hex_layer (h3_index);

ALTER TABLE prism_hex_layer ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE prism_hex_layer IS 'R8 source-of-truth: (hex, layer) intersections';
