#!/usr/bin/env bash
# Create PostgreSQL role and empty database for ai_editor.
# Tables and indexes are created by the application (CodeDatabase sync_schema).
#
# Credentials (same sources as the app):
#   - .env via load_dotenv_near_config (see ai_editor.core.env_loader)
#   - ai_editor.database.driver.config (user, dbname, host, port, password_env)
#   - app password: resolve_pg_password / load_postgres_cli_config
#     (ai_editor.core.postgres_cli_backup)
#
# Superuser for psql (CREATE ROLE / CREATE DATABASE), after .env load:
#   POSTGRES_SUPERUSER_PASSWORD or POSTGRES_ADMIN_PASSWORD or POSTGRES_PASSWORD or PGPASSWORD
#   POSTGRES_SUPERUSER_USER or PGUSER (default postgres)
#
# Usage (from repo root, with .env and config):
#   ./scripts/setup_postgres_ai_editor_db.sh
#   ./scripts/setup_postgres_ai_editor_db.sh path/to/config-venv.json
#   CONFIG_PATH=... ./scripts/setup_postgres_ai_editor_db.sh
#
# Optional:
#   FIX_EXISTING_DB_OWNER=yes   if DB already exists, ALTER DATABASE ... OWNER TO app user

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

if [[ "${1:-}" == "--config" && -n "${2:-}" ]]; then
  CONFIG_PATH="$2"
elif [[ -n "${1:-}" && "${1:0:1}" != "-" ]]; then
  CONFIG_PATH="$1"
else
  CONFIG_PATH="${CONFIG_PATH:-${CASMGR_CONFIG:-}}"
fi

if [[ -z "${CONFIG_PATH}" ]]; then
  if [[ -f "${REPO_ROOT}/config-venv.json" ]]; then
    CONFIG_PATH="${REPO_ROOT}/config-venv.json"
  elif [[ -f "${REPO_ROOT}/config.json" ]]; then
    CONFIG_PATH="${REPO_ROOT}/config.json"
  else
    echo "ERROR: set CONFIG_PATH or pass config file as first argument" >&2
    exit 1
  fi
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "ERROR: config file not found: ${CONFIG_PATH}" >&2
  exit 1
fi

PYTHON="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

eval "$("${PYTHON}" "${SCRIPT_DIR}/setup_postgres_ai_editor_credentials.py" \
  "${CONFIG_PATH}" "${REPO_ROOT}")"

FIX_OWNER="${FIX_EXISTING_DB_OWNER:-}"

if [[ -z "${SETUP_PG_SUPER_PASS}" ]]; then
  echo "ERROR: set superuser password in .env, e.g. POSTGRES_SUPERUSER_PASSWORD" >&2
  echo "       (or POSTGRES_PASSWORD / PGPASSWORD after loading .env)" >&2
  exit 1
fi

if [[ -z "${SETUP_PG_APP_PASS}" ]]; then
  echo "ERROR: app DB password missing (see password_env in config and .env)" >&2
  exit 1
fi

export PGHOST="${SETUP_PG_HOST}"
export PGPORT="${SETUP_PG_PORT}"
export PGUSER="${SETUP_PG_SUPER_USER}"
export PGPASSWORD="${SETUP_PG_SUPER_PASS}"
export PGDATABASE="${PGDATABASE:-postgres}"

APP_ROLE="${SETUP_PG_APP_USER}"
DB_NAME="${SETUP_PG_DBNAME}"
AI_EDITOR_DB_PASSWORD="${SETUP_PG_APP_PASS}"

if ! [[ "${DB_NAME}" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "ERROR: database name must be alphanumeric/underscore only: ${DB_NAME}" >&2
  exit 1
fi

if ! [[ "${APP_ROLE}" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "ERROR: app role name must be alphanumeric/underscore only: ${APP_ROLE}" >&2
  exit 1
fi

psql_v() {
  psql -v ON_ERROR_STOP=1 "$@"
}

echo "==> Ensuring role ${APP_ROLE} exists"
# psql does not expand :'var' inside DO $$ ... $$ (dollar-quote); use plain SQL here.
if [[ "$(psql_v -Atc "SELECT 1 FROM pg_roles WHERE rolname='${APP_ROLE}'")" == "1" ]]; then
  echo "    Role ${APP_ROLE} already exists"
else
  psql_v \
    -v "dbpass=${AI_EDITOR_DB_PASSWORD}" \
    -v "app_role=${APP_ROLE}" \
    -c "CREATE ROLE :\"app_role\" LOGIN PASSWORD :'dbpass';"
  echo "    Created role ${APP_ROLE}"
fi

echo "==> Setting role password (also updates if role already existed)"
psql_v \
  -v "dbpass=${AI_EDITOR_DB_PASSWORD}" \
  -v "app_role=${APP_ROLE}" \
  <<SQL
ALTER ROLE :"app_role" WITH LOGIN PASSWORD :'dbpass';
SQL

echo "==> Ensuring database ${DB_NAME} exists"
exists="$(psql_v -Atc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'")"
if [[ "${exists}" != "1" ]]; then
  psql_v -c "CREATE DATABASE \"${DB_NAME}\" OWNER ${APP_ROLE}"
  echo "    Created database ${DB_NAME} (owner ${APP_ROLE})"
else
  echo "    Database ${DB_NAME} already exists"
  if [[ "${FIX_OWNER}" == "yes" ]] || [[ "${FIX_OWNER}" == "true" ]] || [[ "${FIX_OWNER}" == "1" ]]; then
    echo "==> FIX_EXISTING_DB_OWNER: setting owner to ${APP_ROLE}"
    psql_v -c "ALTER DATABASE \"${DB_NAME}\" OWNER TO ${APP_ROLE}"
  fi
fi

echo "==> Grants on database and schema public (app creates tables via sync_schema)"
psql_v -d "${DB_NAME}" -v "db_name=${DB_NAME}" -v "app_role=${APP_ROLE}" <<'SQL'
GRANT CONNECT ON DATABASE :"db_name" TO :"app_role";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_role";
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO :"app_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO :"app_role";
SQL

echo "Done. Example DSN:"
echo "  postgresql://${APP_ROLE}:<password>@${PGHOST}:${PGPORT}/${DB_NAME}"
