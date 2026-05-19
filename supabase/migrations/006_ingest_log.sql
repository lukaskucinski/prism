-- Structured log for the Python pipeline. Operators inspect this to debug
-- failed layer ingests and validate end-to-end runs.

CREATE TABLE prism_ingest_log (
  id                  BIGSERIAL PRIMARY KEY,
  ts                  TIMESTAMPTZ DEFAULT now(),
  layer_id            TEXT REFERENCES prism_layers(layer_id) ON DELETE SET NULL,
  action              TEXT NOT NULL
                      CHECK (action IN ('seed','query','convert','h3_index','aggregate','score','clean','error')),
  status              TEXT NOT NULL CHECK (status IN ('ok','warn','fail','skip')),
  duration_ms         INTEGER,
  features_processed  INTEGER,
  hexes_written       INTEGER,
  message             TEXT,
  payload             JSONB
);
CREATE INDEX prism_ingest_log_layer_idx ON prism_ingest_log (layer_id, ts DESC);
CREATE INDEX prism_ingest_log_status_idx ON prism_ingest_log (status, ts DESC);

ALTER TABLE prism_ingest_log ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE prism_ingest_log IS 'Append-only ingest/index/score event log';
