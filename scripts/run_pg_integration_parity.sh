#!/usr/bin/env bash
# Run SQLite + PostgreSQL parity tests when AI_EDITOR_POSTGRES_TEST_DSN is set.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi
if [[ -z "${AI_EDITOR_POSTGRES_TEST_DSN:-}" ]]; then
  echo "AI_EDITOR_POSTGRES_TEST_DSN is not set; export a postgresql:// URL to run PG parity." >&2
  exit 1
fi
exec pytest \
  tests/test_postgres_driver_retry.py \
  tests/test_postgres_retry_contract_integration.py \
  tests/test_worker_project_activity.py \
  tests/test_watcher_indexer_project_coordination.py \
  "$@"
