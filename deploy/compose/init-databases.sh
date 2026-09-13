#!/bin/sh
set -eu
# psql variables quote credentials as SQL literals. No secret is printed.
psql --username "$POSTGRES_USER" --dbname postgres -v ON_ERROR_STOP=1 \
  -v app_password="$HEARTH_APP_PASSWORD" -v migration_password="$HEARTH_MIGRATION_PASSWORD" \
  -v identity_password="$HEARTH_IDENTITY_PASSWORD" <<'SQL'
CREATE ROLE hearth_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'migration_password';
CREATE ROLE hearth_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_password';
CREATE ROLE hearth_identity LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'identity_password';
CREATE DATABASE hearth OWNER hearth_migrator;
CREATE DATABASE hearth_identity OWNER hearth_identity;
REVOKE ALL ON DATABASE hearth FROM PUBLIC;
GRANT CONNECT ON DATABASE hearth TO hearth_app, hearth_migrator;
SQL
psql --username "$POSTGRES_USER" --dbname hearth -v ON_ERROR_STOP=1 <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO hearth_app;
GRANT USAGE, CREATE ON SCHEMA public TO hearth_migrator;
SQL
