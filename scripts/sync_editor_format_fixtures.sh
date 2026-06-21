#!/usr/bin/env bash
# Sync tests/fixtures/editor_format_test/test_run/* to the CA watch project tree.
# Usage (on host with watch catalog mounted):
#   EDITOR_FORMAT_TEST_ROOT=/path/to/editor_format_test ./scripts/sync_editor_format_fixtures.sh
set -euo pipefail
ROOT="${EDITOR_FORMAT_TEST_ROOT:?Set EDITOR_FORMAT_TEST_ROOT to editor_format_test project root}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/tests/fixtures/editor_format_test/test_run"
DEST="$ROOT/test_run"
mkdir -p "$DEST"
cp -v "$SRC"/* "$DEST/"
echo "Synced editor_format_test fixtures to $DEST"
