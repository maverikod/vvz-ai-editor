#!/bin/bash
# Shared settings layer for the ai-editor-docker package.
#
# Sources /etc/default/ai-editor, applies a built-in default for every setting the
# package knows about, and derives the values that are computed rather than stored.
# Sourcing this file guarantees that every ${AI_EDITOR_*} placeholder used by
# /etc/ai-editor/ai_editor_container.json has a value, even when an upgrade kept an
# older conffile that predates the newer settings.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

AI_EDITOR_SETTINGS_FILE="${AI_EDITOR_SETTINGS_FILE:-/etc/default/ai-editor}"

if [ -f "$AI_EDITOR_SETTINGS_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$AI_EDITOR_SETTINGS_FILE"
  set +a
fi

set -a

# Host identity and layout.
: "${AI_EDITOR_USER:=ai-editor}"
: "${AI_EDITOR_GROUP:=ai-editor}"
: "${AI_EDITOR_PORT:=15000}"
: "${AI_EDITOR_CONFIG_DIR:=/etc/ai-editor}"
: "${AI_EDITOR_CONFIG_FILE:=ai_editor_container.json}"
: "${AI_EDITOR_LOG_DIR:=/var/log/ai-editor}"
: "${AI_EDITOR_DATA_DIR:=/var/ai-editor}"
: "${AI_EDITOR_PROJECTS_DIR:=/var/casmgr/watch_catalog}"
: "${AI_EDITOR_MTLS_DIR:=/etc/ai-editor/mtls_certificates}"
: "${AI_EDITOR_MTLS_CONTAINER_DIR:=/app/mtls_certificates}"

# Container and Docker networking. Peers are addressed by Docker DNS name on the
# primary network, never by IP.
: "${AI_EDITOR_CONTAINER:=ai-editor}"
: "${AI_EDITOR_NETWORK_PRIMARY:=smart-assistant}"
: "${AI_EDITOR_NETWORK_SECONDARY:=ai-editor-net}"
: "${AI_EDITOR_DOCKER_DNS_NAME:=ai-editor-server}"
: "${AI_EDITOR_SHM_SIZE:=1g}"
: "${AI_EDITOR_ULIMIT_NOFILE:=65536:65536}"

# Connection surface resolved into the service config.
: "${AI_EDITOR_BIND_HOST:=0.0.0.0}"
: "${AI_EDITOR_ADVERTISED_HOST:=ai-editor-server}"
: "${AI_EDITOR_PROTOCOL:=https}"
: "${AI_EDITOR_REGISTRATION_HOST:=mcp-proxy}"
: "${AI_EDITOR_REGISTRATION_PORT:=3004}"
: "${AI_EDITOR_REGISTRATION_PROTOCOL:=https}"
: "${AI_EDITOR_CODE_ANALYSIS_HOST:=casmgr}"
: "${AI_EDITOR_CODE_ANALYSIS_PORT:=15010}"
: "${AI_EDITOR_CODE_ANALYSIS_PROTOCOL:=https}"
: "${AI_EDITOR_SERVER_ID_SUFFIX:=-vvz}"

# Certificate paths as the container sees them (below AI_EDITOR_MTLS_CONTAINER_DIR).
: "${AI_EDITOR_SERVER_SSL_CERT:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/server/ai-editor-server.crt}"
: "${AI_EDITOR_SERVER_SSL_KEY:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/server/ai-editor-server.key}"
: "${AI_EDITOR_SERVER_SSL_CA:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/ca/ca.crt}"
: "${AI_EDITOR_CLIENT_SSL_CERT:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/client/ai-editor.crt}"
: "${AI_EDITOR_CLIENT_SSL_KEY:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/client/ai-editor.key}"
: "${AI_EDITOR_CLIENT_SSL_CA:=${AI_EDITOR_MTLS_CONTAINER_DIR}/mtls_certificates/ca/ca.crt}"

# Derived, never stored: the URL scheme of the registration endpoints. "mtls" is a
# transport mode, not a URL scheme, so it maps onto https.
case "${AI_EDITOR_REGISTRATION_PROTOCOL}" in
  http) AI_EDITOR_REGISTRATION_SCHEME="http" ;;
  *) AI_EDITOR_REGISTRATION_SCHEME="https" ;;
esac

set +a

# Every variable the container must receive so the config template resolves inside it.
AI_EDITOR_PLACEHOLDER_VARS=(
  AI_EDITOR_BIND_HOST
  AI_EDITOR_ADVERTISED_HOST
  AI_EDITOR_PROTOCOL
  AI_EDITOR_REGISTRATION_HOST
  AI_EDITOR_REGISTRATION_PORT
  AI_EDITOR_REGISTRATION_PROTOCOL
  AI_EDITOR_REGISTRATION_SCHEME
  AI_EDITOR_CODE_ANALYSIS_HOST
  AI_EDITOR_CODE_ANALYSIS_PORT
  AI_EDITOR_CODE_ANALYSIS_PROTOCOL
  AI_EDITOR_SERVER_ID_SUFFIX
  AI_EDITOR_SERVER_SSL_CERT
  AI_EDITOR_SERVER_SSL_KEY
  AI_EDITOR_SERVER_SSL_CA
  AI_EDITOR_CLIENT_SSL_CERT
  AI_EDITOR_CLIENT_SSL_KEY
  AI_EDITOR_CLIENT_SSL_CA
)
