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
print(m.group(1) if m else "1.0.6")
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
IP_HOST_NUM="${IP_HOST_NUM:-4}"
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

docker_network_read_subnet() {
  local net="$1"
  docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{"\n"}}{{end}}' 2>/dev/null \
    | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/' | head -1
}

container_ip_from_subnet() {
  local subnet="$1"
  local hostnum="$2"
  python3 -c "
import ipaddress, sys
subnet, hostnum = sys.argv[1], int(sys.argv[2])
net = ipaddress.ip_network(subnet, strict=False)
octets = str(net.network_address).split('.')
octets[3] = str(hostnum)
ip = '.'.join(octets)
if ipaddress.ip_address(ip) not in net:
    sys.exit(1)
print(ip)
" "$subnet" "$hostnum"
}

mkdir -p "$PROJECT_ROOT/docker/data/logs" "$PROJECT_ROOT/docker/data/data" \
  "$PROJECT_ROOT/config" "$PROJECT_ROOT/mtls_certificates"

if [ ! -f "$PROJECT_ROOT/config/$CONFIG_FILE" ]; then
  echo "[ERROR] Config not found: $PROJECT_ROOT/config/$CONFIG_FILE" >&2
  exit 1
fi

docker_ensure_network "$NETWORK_NAME"
docker_ensure_network "$SECOND_NETWORK"

SUBNET="$(docker_network_read_subnet "$NETWORK_NAME")"
STATIC_IP="$(container_ip_from_subnet "$SUBNET" "$IP_HOST_NUM")"
echo "[INFO] Network $NETWORK_NAME subnet=$SUBNET static_ip=$STATIC_IP"

docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --shm-size=1g \
  --ulimit "nofile=${DOCKER_ULIMIT_NOFILE}" \
  --add-host host.docker.internal:host-gateway \
  --network "$NETWORK_NAME" \
  --ip "$STATIC_IP" \
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
  "$IMAGE_NAME"

docker network connect "$SECOND_NETWORK" "$CONTAINER_NAME" 2>/dev/null \
  || echo "[WARN] Failed to connect to $SECOND_NETWORK"

echo "[SUCCESS] Container $CONTAINER_NAME started (port $PORT)"
echo "  curl -k https://localhost:${PORT}/health"
docker ps --filter "name=${CONTAINER_NAME}"
