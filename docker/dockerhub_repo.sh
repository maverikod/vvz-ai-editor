#!/bin/bash
# Resolve Docker Hub image repository for ai-editor builds.
# shellcheck shell=bash

dockerhub_repo_default() {
  if [ -n "${AI_EDITOR_DOCKERHUB_REPO:-}" ]; then
    printf '%s\n' "$AI_EDITOR_DOCKERHUB_REPO"
    return 0
  fi
  local user=""
  if command -v docker >/dev/null 2>&1; then
    user="$(docker info 2>/dev/null | sed -n 's/^ Username: //p' | head -1 | tr -d '[:space:]')"
  fi
  if [ -z "$user" ] && [ -n "${AI_EDITOR_DOCKERHUB_USERNAME:-}" ]; then
    user="$AI_EDITOR_DOCKERHUB_USERNAME"
  fi
  if [ -z "$user" ]; then
    user="vasilyvz"
  fi
  printf '%s/ai-editor\n' "$user"
}

dockerhub_logged_in_user() {
  if ! command -v docker >/dev/null 2>&1; then
    return 0
  fi
  docker info 2>/dev/null | sed -n 's/^ Username: //p' | head -1 | tr -d '[:space:]'
}
