#!/bin/bash
# Post-install reminder: set real values for config placeholders before start.
#
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com

cat <<'EOF'

================================================================================
  AI Editor Docker — configuration required before first start
================================================================================

  The installed config (/etc/ai-editor/ai_editor_container.json) contains
  ${AI_EDITOR_*} placeholders. Set real hostnames or IP addresses on the host:

    sudo editor /etc/default/ai-editor

  Required variables:
    AI_EDITOR_ADVERTISED_HOST       — host/IP advertised to MCP clients
    AI_EDITOR_REGISTRATION_HOST     — MCP proxy registration host
    AI_EDITOR_CODE_ANALYSIS_HOST    — Code Analysis Server (direct JSON-RPC)

  Optional (defaults apply if omitted):
    AI_EDITOR_REGISTRATION_PORT     — default 3004

  Install mTLS material under:
    /etc/ai-editor/mtls_certificates/

  Validate, then recreate and start the container:

    sudo /usr/lib/ai-editor/config-preflight.sh
    sudo ai-editor-docker recreate

  The systemd service refuses to start until placeholders are resolved and
  the configuration passes validation.

================================================================================

EOF
