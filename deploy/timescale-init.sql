-- Runs once on first start of the TimescaleDB container.
--
-- Only the extension is created here. The ORM creates the tables at API
-- startup, which is *after* these init scripts run, so the hypertable
-- conversion cannot happen here (the table would not exist yet and the init
-- script would abort the container). The API applies it idempotently once the
-- tables exist -- see app/database.py:ensure_timeseries().
CREATE EXTENSION IF NOT EXISTS timescaledb;
