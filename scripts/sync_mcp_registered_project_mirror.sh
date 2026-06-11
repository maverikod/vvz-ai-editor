#!/usr/bin/env bash
# Sync primary repo tree into the MCP-registered mirror under test_data/ai-editor-server
# so list_project_files / AST paths match the working copy. Excludes heavy ephemera.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${AI_EDITOR_MCP_MIRROR_ROOT:-$ROOT/test_data/ai-editor-server}"
mkdir -p "$DEST"
rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.mypy_cache/' \
  "$ROOT/" "$DEST/"
echo "Synced $ROOT -> $DEST"
