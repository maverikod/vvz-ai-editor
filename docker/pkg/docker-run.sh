#!/bin/bash
# Production Docker run helper for Debian package (host paths under /etc, /var).
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -e

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f /etc/default/ai-editor ] && . /etc/default/ai-editor
# shellcheck source=/dev/null
[ -f "${LIB_DIR}/image-spec" ] && . "${LIB_DIR}/image-spec"

AI_EDITOR_USER="${AI_EDITOR_USER:-ai-editor}"
AI_EDITOR_GROUP="${AI_EDITOR_GROUP:-ai-editor}"
CONTAINER_NAME="${AI_EDITOR_CONTAINER:-ai-editor}"
PORT="${AI_EDITOR_PORT:-15000}"
CONFIG_DIR="${AI_EDITOR_CONFIG_DIR:-/etc/ai-editor}"
CONFIG_FILE="${AI_EDITOR_CONFIG_FILE:-ai_editor_container.json}"
LOG_DIR="${AI_EDITOR_LOG_DIR:-/var/log/ai-editor}"
DATA_DIR="${AI_EDITOR_DATA_DIR:-/var/ai-editor}"
MTLS_DIR="${AI_EDITOR_MTLS_DIR:-/etc/ai-editor/mtls_certificates}"
NETWORK_PRIMARY="${AI_EDITOR_NETWORK_PRIMARY:-smart-assistant}"
NETWORK_SECONDARY="${AI_EDITOR_NETWORK_SECONDARY:-ai-editor-net}"
IP_HOST_NUM="${AI_EDITOR_IP_HOST_NUM:-4}"
DNS_NAME="${AI_EDITOR_DOCKER_DNS_NAME:-ai-editor-server}"
SHM_SIZE="${AI_EDITOR_SHM_SIZE:-1g}"
ULIMIT_NOFILE="${AI_EDITOR_ULIMIT_NOFILE:-65536:65536}"
IMAGE_SPEC="${LIB_DIR}/image-spec"

LAST_DOCKER_SUBNET=""
SMART_ASSISTANT_CONTAINER_IP=""
EXTRA_HOST_DOCKER_ARGS=()

if [ -f "$IMAGE_SPEC" ]; then
  # shellcheck source=/dev/null
  . "$IMAGE_SPEC"
fi
IMAGE_NAME="${DOCKERHUB_REPO:-ai-editor}:${IMAGE_TAG:-latest}"

ensure_host_owner() {
  if ! getent passwd "$AI_EDITOR_USER" >/dev/null 2>&1; then
    echo "[ERROR] Host system user not found: ${AI_EDITOR_USER}" >&2
    exit 1
  fi
  if ! getent group "$AI_EDITOR_GROUP" >/dev/null 2>&1; then
    echo "[ERROR] Host system group not found: ${AI_EDITOR_GROUP}" >&2
    exit 1
  fi
}

container_run_user() {
  AI_EDITOR_UID="$(id -u "$AI_EDITOR_USER")"
  AI_EDITOR_GID="$(id -g "$AI_EDITOR_GROUP")"
  printf '%s:%s' "$AI_EDITOR_UID" "$AI_EDITOR_GID"
}

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
  local out
  out=$(docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{"\n"}}{{end}}' 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/' | head -1)
  if [ -z "$out" ]; then
    echo "[ERROR] no IPv4 subnet in Docker IPAM for network \"$net\"" >&2
    return 1
  fi
  printf '%s' "$out"
}

container_ip_from_subnet() {
  local subnet="$1"
  local hostnum="$2"
  python3 -c "
import ipaddress, sys
subnet, hostnum = sys.argv[1], int(sys.argv[2])
if not 0 <= hostnum <= 255:
    sys.exit('IP_HOST_NUM out of range')
net = ipaddress.ip_network(subnet, strict=False)
octets = str(net.network_address).split('.')
octets[3] = str(hostnum)
ip = '.'.join(octets)
if ipaddress.ip_address(ip) not in net:
    print(f'Error: {ip} not in {subnet}', file=sys.stderr)
    sys.exit(1)
print(ip)
" "$subnet" "$hostnum"
}

smart_assistant_prepare_static_ip() {
  local net="$1"
  docker_ensure_network "$net"
  local subnet
  subnet=$(docker_network_read_subnet "$net") || return 1
  local target_ip
  target_ip=$(container_ip_from_subnet "$subnet" "$IP_HOST_NUM") || return 1
  echo "[INFO] Network \"$net\": subnet $subnet → container IP $target_ip (IP_HOST_NUM=$IP_HOST_NUM)"
  LAST_DOCKER_SUBNET="$subnet"
  SMART_ASSISTANT_CONTAINER_IP="$target_ip"
}

container_create() {
  local -a docker_opts
  local config_in_container="/etc/ai-editor/${CONFIG_FILE}"

  ensure_host_owner
  mkdir -p "$CONFIG_DIR" "$LOG_DIR" "${DATA_DIR}/editor_workspaces" "${DATA_DIR}/versions" "$MTLS_DIR"
  chown -R "${AI_EDITOR_USER}:${AI_EDITOR_GROUP}" "$LOG_DIR" "$DATA_DIR" 2>/dev/null || true
  chmod 755 "$LOG_DIR" "$DATA_DIR" 2>/dev/null || true

  if [ ! -f "${CONFIG_DIR}/${CONFIG_FILE}" ]; then
    echo "[ERROR] Config not found: ${CONFIG_DIR}/${CONFIG_FILE}" >&2
    exit 1
  fi

  smart_assistant_prepare_static_ip "$NETWORK_PRIMARY" || exit 1
  docker_ensure_network "$NETWORK_SECONDARY"
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

  docker_opts=(
    --name "$CONTAINER_NAME"
    --user "$(container_run_user)"
    --shm-size "$SHM_SIZE"
    --ulimit "nofile=$ULIMIT_NOFILE"
    -v "${CONFIG_DIR}/${CONFIG_FILE}:${config_in_container}:ro"
    -v "${LOG_DIR}:/var/log/ai-editor"
    -v "${DATA_DIR}:/var/ai-editor"
    -v "${MTLS_DIR}:/app/mtls_certificates:ro"
    --network "$NETWORK_PRIMARY"
    --ip "$SMART_ASSISTANT_CONTAINER_IP"
    --network-alias "$CONTAINER_NAME"
    --network-alias "$DNS_NAME"
    -p "${PORT}:15000"
    -e "CONFIG_FILE=${CONFIG_FILE}"
    -e PYTHONUNBUFFERED=1
    --add-host host.docker.internal:host-gateway
    --restart=always
  )

  if [ -n "${AI_EDITOR_POSTGRES_PASSWORD:-}" ]; then
    docker_opts+=(-e "AI_EDITOR_POSTGRES_PASSWORD=${AI_EDITOR_POSTGRES_PASSWORD}")
  fi

  if [ "${#EXTRA_HOST_DOCKER_ARGS[@]}" -gt 0 ]; then
    docker_opts+=("${EXTRA_HOST_DOCKER_ARGS[@]}")
  fi

  echo "[INFO] Creating container (image=$IMAGE_NAME, user=$(container_run_user))"
  docker create "${docker_opts[@]}" "$IMAGE_NAME"
  docker network connect "$NETWORK_SECONDARY" "$CONTAINER_NAME" 2>/dev/null \
    || echo "[WARN] Failed to connect to $NETWORK_SECONDARY network"
}

container_image_matches() {
  local current=""
  current="$(docker inspect "$CONTAINER_NAME" --format '{{.Config.Image}}' 2>/dev/null || true)"
  [ "$current" = "$IMAGE_NAME" ]
}

start_container() {
  docker start "$CONTAINER_NAME"
}

pull_image_if_requested() {
  if [ "${AI_EDITOR_PULL_ON_RECREATE:-0}" != "1" ]; then
    return 0
  fi
  echo "[INFO] Pulling $IMAGE_NAME ..."
  docker pull "$IMAGE_NAME"
}

cmd_start() {
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    if ! container_image_matches; then
      echo "[INFO] Recreating $CONTAINER_NAME (image changed -> $IMAGE_NAME)"
      docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    fi
  fi
  if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    container_create
  fi
  start_container
  echo "[SUCCESS] Container $CONTAINER_NAME started (user=$(container_run_user), port=$PORT)"
}

cmd_stop() {
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
}

cmd_restart() {
  if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    cmd_start
    return
  fi
  cmd_stop
  docker start "$CONTAINER_NAME"
  echo "[SUCCESS] Container $CONTAINER_NAME restarted (same instance)"
}

cmd_recreate() {
  pull_image_if_requested
  cmd_stop
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  container_create
  start_container
  echo "[SUCCESS] Container $CONTAINER_NAME recreated (user=$(container_run_user), port=$PORT)"
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  recreate) cmd_recreate ;;
  *)
    echo "Usage: $0 {start|stop|restart|recreate}" >&2
    exit 1
    ;;
esac
