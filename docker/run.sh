#!/bin/bash
# Local dev: create/start ai-editor container with project bind mounts.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"

IMAGE_VERSION="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
print(m.group(1) if m else "1.0.7")
PY
)"
DEFAULT_IMAGE="$(dockerhub_repo_default):${IMAGE_VERSION}"
IMAGE_NAME="${AI_EDITOR_DEV_IMAGE:-$DEFAULT_IMAGE}"
CONTAINER_NAME="${AI_EDITOR_CONTAINER:-ai-editor}"
PORT="${AI_EDITOR_PORT:-15000}"
CONFIG_FILE="${CONFIG_FILE:-ai_editor_container.json}"
DOCKER_ULIMIT_NOFILE="${DOCKER_ULIMIT_NOFILE:-65536:65536}"
NETWORK_NAME="${NET_NAME:-smart-assistant}"
SECOND_NETWORK="${SECOND_DOCKER_NETWORK:-ai-editor-net}"
DNS_DOMAIN="${DOCKER_DNS_DOMAIN:-}"
DNS_NAME="${DOCKER_DNS_NAME:-ai-editor-server}"

if [ -f "$SCRIPT_DIR/container.env" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/container.env"
fi
if [ -f "$SCRIPT_DIR/container.env.local" ]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/container.env.local"
fi

ENV_FILE_ARGS=()
if [ -f "$SCRIPT_DIR/container.env" ]; then
  ENV_FILE_ARGS=(--env-file "$SCRIPT_DIR/container.env")
fi
if [ -f "$SCRIPT_DIR/container.env.local" ]; then
  ENV_FILE_ARGS+=(--env-file "$SCRIPT_DIR/container.env.local")
fi

docker_ensure_network() {
  local net="$1"
  [ -n "$net" ] || return 0
  if docker network inspect "$net" >/dev/null 2>&1; then
    return 0
  fi
  docker network create "$net"
}

mkdir -p "$PROJECT_ROOT/docker/data/logs" "$PROJECT_ROOT/docker/data/data" \
  "$PROJECT_ROOT/config" "$PROJECT_ROOT/mtls_certificates"

if [ ! -f "$PROJECT_ROOT/config/$CONFIG_FILE" ]; then
  BUNDLED="$PROJECT_ROOT/ai_editor/config_templates/$CONFIG_FILE"
  if [ -f "$BUNDLED" ]; then
    cp "$BUNDLED" "$PROJECT_ROOT/config/$CONFIG_FILE"
    echo "[INFO] Copied bundled template to config/$CONFIG_FILE"
  else
    echo "[ERROR] Config not found: $PROJECT_ROOT/config/$CONFIG_FILE" >&2
    echo "[ERROR] Run: python scripts/sync_container_config_template.py" >&2
    exit 1
  fi
fi

docker_ensure_network "$NETWORK_NAME"
docker_ensure_network "$SECOND_NETWORK"

docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --workdir /var/log/ai-editor \
  --shm-size=1g \
  --ulimit "nofile=${DOCKER_ULIMIT_NOFILE}" \
  --add-host host.docker.internal:host-gateway \
  --network "$NETWORK_NAME" \
  --network-alias "$CONTAINER_NAME" \
  --network-alias "$DNS_NAME" \
  -v "$PROJECT_ROOT/config:/etc/ai-editor:ro" \
  -v "$PROJECT_ROOT/mtls_certificates:/app/mtls_certificates:ro" \
  -v "$PROJECT_ROOT/docker/data/logs:/var/log/ai-editor" \
  -v "$PROJECT_ROOT/docker/data/data:/var/ai-editor" \
  -p "${PORT}:15000" \
  "${ENV_FILE_ARGS[@]}" \
  -e "CONFIG_FILE=${CONFIG_FILE}" \
  -e PYTHONUNBUFFERED=1 \
  -e "HOME=/var/log/ai-editor" \
  "$IMAGE_NAME"

docker network connect "$SECOND_NETWORK" "$CONTAINER_NAME" 2>/dev/null \
  || echo "[WARN] Failed to connect to $SECOND_NETWORK"

echo "[SUCCESS] Container $CONTAINER_NAME started (port $PORT)"
echo "  curl -k https://localhost:${PORT}/health"
docker ps --filter "name=${CONTAINER_NAME}"
