-- Run once, as the postgres superuser, to create the local dev role and
-- databases this project's DATABASE_URL / TEST_DATABASE_URL point at.
--
--   psql -U postgres -h localhost -f scripts/setup_local_db.sql
--
CREATE ROLE erp WITH LOGIN PASSWORD 'erp';
CREATE DATABASE erp OWNER erp;
CREATE DATABASE erp_test OWNER erp;

-- Owning the database is not enough on Postgres 15+: the `public` schema
-- inside a new database is still owned by whoever ran CREATE DATABASE
-- (the postgres superuser here), not its database's owner. The test
-- fixture drops and recreates `public` between test runs for a guaranteed
-- clean slate, which requires actually owning the schema, not just having
-- privileges on it.
\c erp
ALTER SCHEMA public OWNER TO erp;
\c erp_test
ALTER SCHEMA public OWNER TO erp;
