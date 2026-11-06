-- NEW DESIGN 2026-11-06. Not recovered 2026-11-05 DDL.
-- DuckDB 1.4.3; ISO dates are exchange-local dates; timestamps are UTC instants.
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY, description VARCHAR NOT NULL);
INSERT INTO schema_version VALUES (1, 'Portable research warehouse, reconstructed 2026-11-06') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS ingestion_batch (
  batch_id VARCHAR PRIMARY KEY,
  kind VARCHAR NOT NULL,
  source VARCHAR NOT NULL,
  source_revision VARCHAR NOT NULL,
  retrieved_at TIMESTAMPTZ NOT NULL,
  available_at TIMESTAMPTZ NOT NULL,
  input_sha256 VARCHAR NOT NULL CHECK(length(input_sha256) = 64),
  normalizer_version VARCHAR NOT NULL,
  row_count BIGINT NOT NULL CHECK(row_count >= 0),
  metadata_json JSON NOT NULL,
  CHECK(available_at >= retrieved_at)
);
CREATE TABLE IF NOT EXISTS instrument_lifecycle (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL,
  exchange VARCHAR NOT NULL CHECK(exchange IN ('SSE','SZSE','BSE')),
  listed_on DATE NOT NULL,
  delisted_on DATE,
  PRIMARY KEY(batch_id, instrument),
  CHECK(delisted_on IS NULL OR delisted_on >= listed_on)
);
CREATE TABLE IF NOT EXISTS trading_calendar (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  exchange VARCHAR NOT NULL CHECK(exchange IN ('SSE','SZSE','BSE')),
  date DATE NOT NULL,
  is_open BOOLEAN NOT NULL,
  PRIMARY KEY(batch_id, exchange, date)
);
CREATE TABLE IF NOT EXISTS daily_price (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL,
  date DATE NOT NULL,
  price_basis VARCHAR NOT NULL CHECK(price_basis IN ('unadjusted','qfq','hfq','total_return')),
  adjustment_id VARCHAR NOT NULL,
  open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
  volume_shares DOUBLE, amount_cny DOUBLE, prev_close_reported DOUBLE,
  trade_status VARCHAR NOT NULL CHECK(trade_status IN ('unknown','traded','suspended')),
  PRIMARY KEY(batch_id, instrument, date, price_basis),
  CHECK((price_basis = 'unadjusted' AND adjustment_id = 'none') OR
        (price_basis <> 'unadjusted' AND adjustment_id <> 'none')),
  CHECK((open IS NULL AND high IS NULL AND low IS NULL AND close IS NULL AND trade_status = 'suspended') OR
        (open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL AND
         isfinite(open) AND isfinite(high) AND isfinite(low) AND isfinite(close) AND
         low > 0 AND high >= greatest(open, close) AND low <= least(open, close) AND high >= low)),
  CHECK(volume_shares IS NULL OR (isfinite(volume_shares) AND volume_shares >= 0)),
  CHECK(amount_cny IS NULL OR (isfinite(amount_cny) AND amount_cny >= 0)),
  CHECK(prev_close_reported IS NULL OR (isfinite(prev_close_reported) AND prev_close_reported > 0))
);
-- Factors remain independent evidence, never silently applied to another vendor's prices.
CREATE TABLE IF NOT EXISTS adjustment_factor (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL, date DATE NOT NULL,
  adjustment_id VARCHAR NOT NULL, factor DOUBLE NOT NULL CHECK(isfinite(factor) AND factor > 0),
  available_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(batch_id, instrument, date, adjustment_id)
);
-- Long form is a new storage contract, NOT reconstructed vendor financial columns.
CREATE TABLE IF NOT EXISTS financial_fact (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL, metric VARCHAR NOT NULL,
  period_end DATE NOT NULL, period_start DATE,
  announced_at TIMESTAMPTZ, available_at TIMESTAMPTZ NOT NULL,
  value DOUBLE, unit VARCHAR NOT NULL, statement_version VARCHAR NOT NULL,
  PRIMARY KEY(batch_id, instrument, metric, period_end, statement_version),
  CHECK(period_start IS NULL OR period_start <= period_end),
  CHECK(value IS NULL OR isfinite(value)),
  CHECK(announced_at IS NULL OR available_at >= announced_at)
);
CREATE TABLE IF NOT EXISTS corporate_event (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL, event_id VARCHAR NOT NULL, event_type VARCHAR NOT NULL,
  effective_date DATE, announced_at TIMESTAMPTZ, available_at TIMESTAMPTZ NOT NULL,
  value DOUBLE, unit VARCHAR, quality VARCHAR NOT NULL,
  PRIMARY KEY(batch_id, event_id),
  CHECK(value IS NULL OR isfinite(value)),
  CHECK(announced_at IS NULL OR available_at >= announced_at)
);
CREATE TABLE IF NOT EXISTS daily_limit (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  instrument VARCHAR NOT NULL, date DATE NOT NULL,
  upper_limit DOUBLE, lower_limit DOUBLE, quality VARCHAR NOT NULL,
  PRIMARY KEY(batch_id, instrument, date),
  CHECK(upper_limit IS NULL OR (isfinite(upper_limit) AND upper_limit > 0)),
  CHECK(lower_limit IS NULL OR (isfinite(lower_limit) AND lower_limit > 0)),
  CHECK(lower_limit IS NULL OR upper_limit IS NULL OR lower_limit <= upper_limit)
);
CREATE TABLE IF NOT EXISTS macro_observation (
  batch_id VARCHAR NOT NULL REFERENCES ingestion_batch(batch_id),
  series VARCHAR NOT NULL, observation_date DATE NOT NULL,
  available_at TIMESTAMPTZ NOT NULL, vintage VARCHAR NOT NULL,
  value DOUBLE, unit VARCHAR NOT NULL,
  PRIMARY KEY(batch_id, series, observation_date, vintage),
  CHECK(value IS NULL OR isfinite(value))
);
CREATE TABLE IF NOT EXISTS retrieval_audit (
  query_id VARCHAR PRIMARY KEY, queried_at TIMESTAMPTZ NOT NULL,
  request_json JSON NOT NULL, decision_json JSON NOT NULL
);
-- No default cross-source price view. Selection requires explicit priority and whole-series coverage.
CREATE OR REPLACE VIEW source_coverage AS
SELECT b.batch_id, b.source, b.source_revision, b.available_at, p.instrument,
       p.price_basis, p.adjustment_id, min(p.date) AS first_date, max(p.date) AS last_date, count(*) AS rows
FROM daily_price p JOIN ingestion_batch b USING(batch_id)
GROUP BY ALL;
-- At minimum a value is available after BOTH its evidence time and snapshot acquisition.
-- These views do not certify that supplied announced_at/available_at are historically complete.
CREATE OR REPLACE VIEW financial_fact_observation AS
SELECT f.*, b.source, b.source_revision, b.retrieved_at,
       greatest(f.available_at,b.available_at) AS safe_available_at
FROM financial_fact f JOIN ingestion_batch b USING(batch_id);
CREATE OR REPLACE VIEW macro_vintage_observation AS
SELECT m.*, b.source, b.source_revision, b.retrieved_at,
       greatest(m.available_at,b.available_at) AS safe_available_at
FROM macro_observation m JOIN ingestion_batch b USING(batch_id);
