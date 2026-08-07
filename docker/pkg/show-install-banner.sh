#!/bin/bash
# Post-install banner: what the package configured, and the one thing it cannot.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

MTLS_DIR="${AI_EDITOR_MTLS_DIR:-/etc/ai-editor/mtls_certificates}"

cat <<EOF

================================================================================
  AI Editor Docker — installed and configured
================================================================================

  The package configures the service itself. Every setting is written to
  /etc/default/ai-editor and substituted into
  /etc/ai-editor/ai_editor_container.json when the container starts. No file
  needs to be edited by hand.

  Review or change any setting through the argument surface — it validates the
  value, writes it, and recreates the container:

    ai-editor-config list
    sudo ai-editor-config set --registration-host mcp-proxy --port 15000
    sudo ai-editor-config apply

  Settings cover the host port, bind and advertised host, protocol, the
  registration and Code Analysis endpoints, the certificate paths, the server-id
  suffix, and the Docker networks. See: man ai-editor-config

  The one thing the package cannot supply is the mTLS material itself: private
  keys are copied to the host out of band, before a deploy. Place it under

    ${MTLS_DIR}/

  and the package applies the access rule on every install: owned by
  root:\${AI_EDITOR_GROUP}, directories 750, files 640.

  The service refuses to start until the configuration passes validation.

================================================================================

EOF
