-- Runs once on first start of the postgres/timescale container.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- The ORM creates the tables; this turns price_daily into a hypertable.
-- Kept separate so local sqlite runs (no timescale) still work fine.
SELECT create_hypertable('price_daily', 'date', if_not_exists => TRUE, migrate_data => TRUE);
CREATE INDEX IF NOT EXISTS ix_price_daily_company_date ON price_daily (company_id, date DESC);
