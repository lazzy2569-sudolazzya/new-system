-- Run once, as the postgres superuser, to create the local dev role and
-- databases this project's DATABASE_URL / TEST_DATABASE_URL point at.
--
--   psql -U postgres -h localhost -f scripts/setup_local_db.sql
--
CREATE ROLE erp WITH LOGIN PASSWORD 'erp';
CREATE DATABASE erp OWNER erp;
CREATE DATABASE erp_test OWNER erp;
