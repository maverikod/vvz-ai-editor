#!/bin/bash
# Verify ai-editor service config placeholders before container start.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f /etc/default/ai-editor ]; then
  set -a
  # shellcheck source=/dev/null
  . /etc/default/ai-editor
  set +a
fi

CONFIG_DIR="${AI_EDITOR_CONFIG_DIR:-/etc/ai-editor}"
CONFIG_FILE="${AI_EDITOR_CONFIG_FILE:-ai_editor_container.json}"
CONFIG_PATH="${CONFIG_DIR}/${CONFIG_FILE}"
MTLS_DIR="${AI_EDITOR_MTLS_DIR:-/etc/ai-editor/mtls_certificates}"
IMAGE_SPEC="${LIB_DIR}/image-spec"

export AI_EDITOR_CONFIG_PATH="$CONFIG_PATH"

if [ ! -x "${LIB_DIR}/config_preflight.py" ]; then
  echo "[ai-editor-config] missing ${LIB_DIR}/config_preflight.py" >&2
  exit 1
fi

if ! python3 "${LIB_DIR}/config_preflight.py" "$CONFIG_PATH"; then
  exit 1
fi

if [ "${AI_EDITOR_SKIP_DOCKER_VALIDATE:-0}" = "1" ]; then
  exit 0
fi

if [ ! -f "$IMAGE_SPEC" ]; then
  exit 0
fi

# shellcheck source=/dev/null
. "$IMAGE_SPEC"
IMAGE_NAME="${DOCKERHUB_REPO:-}:${IMAGE_TAG:-}"
if [ -z "$IMAGE_NAME" ] || [ "$IMAGE_NAME" = ":" ]; then
  exit 0
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  exit 0
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  exit 0
fi

config_in_container="/etc/ai-editor/${CONFIG_FILE}"
docker_env_args=()
for _var in \
  AI_EDITOR_ADVERTISED_HOST \
  AI_EDITOR_REGISTRATION_HOST \
  AI_EDITOR_REGISTRATION_PORT \
  AI_EDITOR_CODE_ANALYSIS_HOST \
  AI_EDITOR_CODE_ANALYSIS_PORT \
  AI_EDITOR_POSTGRES_PASSWORD; do
  if [ -n "${!_var:-}" ]; then
    docker_env_args+=(-e "${_var}=${!_var}")
  fi
done

if docker run --rm \
  "${docker_env_args[@]}" \
  -v "${CONFIG_PATH}:${config_in_container}:ro" \
  -v "${MTLS_DIR}:/app/mtls_certificates:ro" \
  --entrypoint aiedcfg \
  "$IMAGE_NAME" \
  validate --file "$config_in_container"; then
  echo "[ai-editor-config] Full configuration validation passed (container image)"
  exit 0
fi

echo "[ai-editor-config] Full validation via Docker image failed (see errors above)" >&2
exit 1
