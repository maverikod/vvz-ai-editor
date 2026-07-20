#!/bin/bash
# Build Docker image, push to Docker Hub, and create Debian package.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck source=dockerhub_repo.sh
source "$SCRIPT_DIR/dockerhub_repo.sh"
DOCKERHUB_REPO="$(dockerhub_repo_default)"
DOCKER_BUILD_NETWORK="${DOCKER_BUILD_NETWORK:-host}"
SKIP_PUSH=0
SKIP_DEB=0
SKIP_LIVE_PIPELINE="${AI_EDITOR_SKIP_LIVE_PIPELINE:-0}"
DEV_RUN=0
TAG=""

usage() {
  cat <<'EOF'
Usage: docker/build.sh [OPTIONS] [VERSION]

Build ai-editor Docker image, push to Docker Hub, and build Debian package.
VERSION defaults to pyproject.toml version. Image tags: REPO:VERSION and REPO:latest.

Options:
  --skip-push     Build image only; do not push to Docker Hub
  --skip-deb      Do not build the Debian package
  --skip-live-pipeline
                  Skip real-server editor->CA pipeline gate
  --dev-run       After build, run local dev container via docker/run.sh
  -h, --help      Show this help

Environment:
  AI_EDITOR_DOCKERHUB_REPO       Docker Hub repository (default: <docker-login-user>/ai-editor)
  AI_EDITOR_DOCKERHUB_USERNAME   Docker Hub username for non-interactive login
  AI_EDITOR_DOCKERHUB_TOKEN      Docker Hub access token (or password)
  DOCKER_BUILD_NETWORK           docker build network (default: host)
  AI_EDITOR_DOCKER_NO_CACHE=1    Pass --no-cache to docker build
  AI_EDITOR_SKIP_LIVE_PIPELINE=1 Skip real-server editor->CA pipeline gate
  AI_EDITOR_CA_HOST/PORT         Override Code Analysis server for live pipeline
  AI_EDITOR_HOST/PORT            Override AI Editor server for live pipeline
  AI_EDITOR_WATCH_DIR_ID         Override CA watch dir; unset auto-discovers
  AI_EDITOR_MTLS_DIR             Override mTLS certificate directory
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-push) SKIP_PUSH=1; shift ;;
    --skip-deb) SKIP_DEB=1; shift ;;
    --skip-live-pipeline) SKIP_LIVE_PIPELINE=1; shift ;;
    --dev-run) DEV_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "[ERROR] Unknown option: $1" >&2; usage >&2; exit 1 ;;
    *) TAG="$1"; shift ;;
  esac
done

if [ -z "$TAG" ]; then
  TAG="$(python3 - <<'PY'
import re
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
if not m:
    raise SystemExit("Cannot read version from pyproject.toml")
print(m.group(1))
PY
)"
fi

VERSION_TAG="${DOCKERHUB_REPO}:${TAG}"
LATEST_TAG="${DOCKERHUB_REPO}:latest"

if [ ! -f "docker/Dockerfile" ]; then
  echo "[ERROR] Dockerfile not found in docker/"
  exit 1
fi
if [ ! -f "requirements.txt" ]; then
  echo "[ERROR] requirements.txt not found (Docker build uses it)"
  exit 1
fi

echo "[INFO] Building Docker image"
echo "[INFO]   version tag: $VERSION_TAG"
echo "[INFO]   latest tag:  $LATEST_TAG"

DOCKER_BUILD_EXTRAS=(--network="$DOCKER_BUILD_NETWORK")
if [ "${AI_EDITOR_DOCKER_NO_CACHE:-}" = "1" ]; then
  DOCKER_BUILD_EXTRAS+=(--no-cache)
  echo "[INFO] AI_EDITOR_DOCKER_NO_CACHE=1: docker build --no-cache"
fi

DF="$PROJECT_ROOT/docker/Dockerfile"
CTX="$PROJECT_ROOT"

if docker buildx version >/dev/null 2>&1; then
  echo "[INFO] using: docker buildx build --load"
  docker buildx build --load "${DOCKER_BUILD_EXTRAS[@]}" -t "$VERSION_TAG" -t "$LATEST_TAG" -f "$DF" "$CTX"
else
  echo "[INFO] using: docker build"
  docker build "${DOCKER_BUILD_EXTRAS[@]}" -t "$VERSION_TAG" -t "$LATEST_TAG" -f "$DF" "$CTX"
fi

echo "[SUCCESS] Image built: $VERSION_TAG and $LATEST_TAG"

if [ "$SKIP_LIVE_PIPELINE" = "1" ]; then
  echo "[INFO] Skipping real-server editor->CA pipeline gate"
else
  if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
  echo "[INFO] Running real-server editor->CA pipeline gate"
  "$PYTHON_BIN" "$PROJECT_ROOT/scripts/verify_editor_ca_chain.py"
  echo "[SUCCESS] Real-server editor->CA pipeline gate passed"
fi

if [ "$SKIP_PUSH" -eq 0 ]; then
  if [ -n "${AI_EDITOR_DOCKERHUB_USERNAME:-}" ] && [ -n "${AI_EDITOR_DOCKERHUB_TOKEN:-}" ]; then
    echo "[INFO] Logging in to Docker Hub as ${AI_EDITOR_DOCKERHUB_USERNAME}"
    echo "$AI_EDITOR_DOCKERHUB_TOKEN" | docker login -u "$AI_EDITOR_DOCKERHUB_USERNAME" --password-stdin
  fi
  REPO_USER="${DOCKERHUB_REPO%%/*}"
  DOCKER_USER="$(dockerhub_logged_in_user)"
  if [ -z "$DOCKER_USER" ]; then
    echo "[ERROR] Not logged in to Docker Hub. Run: docker login -u <user>" >&2
    exit 1
  fi
  if [ "$REPO_USER" != "$DOCKER_USER" ]; then
    echo "[ERROR] Cannot push ${DOCKERHUB_REPO}: logged in as ${DOCKER_USER}." >&2
    echo "[ERROR] Use: export AI_EDITOR_DOCKERHUB_REPO=${DOCKER_USER}/ai-editor" >&2
    exit 1
  fi
  echo "[INFO] Pushing $VERSION_TAG"
  docker push "$VERSION_TAG"
  echo "[INFO] Pushing $LATEST_TAG"
  docker push "$LATEST_TAG"
  echo "[SUCCESS] Images pushed to Docker Hub (${DOCKERHUB_REPO})"
else
  echo "[INFO] Skipping Docker Hub push (--skip-push)"
fi

if [ "$SKIP_DEB" -eq 0 ]; then
  bash "$SCRIPT_DIR/build-deb.sh" "$TAG"
else
  echo "[INFO] Skipping Debian package build (--skip-deb)"
fi

if [ "$DEV_RUN" -eq 1 ]; then
  echo "[INFO] Starting local dev container (project bind mounts)"
  docker tag "$VERSION_TAG" "ai-editor:${TAG}" 2>/dev/null || true
  mkdir -p "$PROJECT_ROOT/docker/data/logs" "$PROJECT_ROOT/docker/data/data" \
    "$PROJECT_ROOT/config" "$PROJECT_ROOT/mtls_certificates"
  exec bash "$SCRIPT_DIR/run.sh"
fi

echo "[DONE] build.sh finished (version=$TAG)"
