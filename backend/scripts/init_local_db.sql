-- Runs once when the local Postgres volume is created.
-- app_migrator (the superuser here) owns every table; app_rw is what the services connect as.
CREATE ROLE app_rw LOGIN PASSWORD 'app_rw';
CREATE DATABASE studyplatform_test OWNER app_migrator;
GRANT CONNECT ON DATABASE studyplatform TO app_rw;
GRANT CONNECT ON DATABASE studyplatform_test TO app_rw;
