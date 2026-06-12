FROM python:3.14-slim

LABEL maintainer="Vasiliy Zdanovskiy <vasilyvz@gmail.com>"
LABEL description="AI Editor MCP server"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_HOME=/app
ENV CONFIG_DIR=/etc/ai-editor
ENV LOG_DIR=/var/log/ai-editor
ENV DATA_DIR=/var/ai-editor

RUN mkdir -p "$APP_HOME" "$CONFIG_DIR" "$LOG_DIR" "$DATA_DIR"

WORKDIR $APP_HOME

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    postgresql-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY ai_editor/ ai_editor/
COPY aiedmgr_entry/ aiedmgr_entry/
COPY scripts/aiedmgr scripts/aiedmgr
COPY scripts/aiedcfg scripts/aiedcfg

RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

RUN mkdir -p "$CONFIG_DIR" && python -c "\
from ai_editor.config_templates import copy_bundled_template; \
copy_bundled_template('${CONFIG_DIR}', overwrite=True)"

RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser && \
    chown -R appuser:appuser "$APP_HOME" && \
    chmod -R a+rX "$APP_HOME"

USER root

EXPOSE 15000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f -sk https://localhost:15000/health || exit 1

CMD ["sh", "-c", "cd \"${LOG_DIR}\" && exec python -m ai_editor.main --config ${CONFIG_DIR}/${CONFIG_FILE:-ai_editor_container.json} --foreground"]
