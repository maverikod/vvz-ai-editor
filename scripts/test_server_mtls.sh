#!/usr/bin/env bash
# Test ai-editor-server with mTLS (curl + client cert).
# Run when the server is listening on 15000.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

set -e
cd "$(dirname "$0")/.."
BASE="mtls_certificates/mtls_certificates"
CA="$BASE/ca/ca.crt"
# Client cert as in config.json (registration / client)
CLIENT_CERT="$BASE/client/ai-editor.crt"
CLIENT_KEY="$BASE/client/ai-editor.key"
HOST="${1:-127.0.0.1}"
PORT="${2:-15000}"
# Root path: server may return 404; use /health if available
URL="https://${HOST}:${PORT}/"

if [[ ! -f "$CA" || ! -f "$CLIENT_CERT" || ! -f "$CLIENT_KEY" ]]; then
  echo "Missing certs: $CA, $CLIENT_CERT, $CLIENT_KEY" >&2
  exit 1
fi

echo "Testing $URL with mTLS (client cert: ai-editor)..."
curl -s --connect-timeout 5 \
  --cert "$CLIENT_CERT" \
  --key  "$CLIENT_KEY" \
  --cacert "$CA" \
  -w "\nHTTP_CODE:%{http_code}\n" \
  "$URL"
echo ""
