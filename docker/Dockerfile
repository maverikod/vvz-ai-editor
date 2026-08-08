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

# VERSION is the single source of truth for the server, the client and the
# engine version. It must land before src/, whose VERSION is a relative symlink
# into this same file (src/VERSION -> ../VERSION); Docker copies the link, not
# its target, so the target has to exist at /app/VERSION.
COPY VERSION ./
COPY requirements.txt pyproject.toml ./
COPY docs/README.md docs/README.md
COPY ai_editor/ ai_editor/
# src/ is the source of the ai-editor-tree-engine DISTRIBUTION, not a directory
# the server imports from. It is copied only because that distribution is not
# published to PyPI yet -- see the install step below.
COPY src/ src/
COPY aiedmgr_entry/ aiedmgr_entry/
COPY scripts/aiedmgr scripts/aiedmgr
COPY scripts/aiedcfg scripts/aiedcfg
COPY scripts/pipeline scripts/pipeline

# One install pass. requirements.txt lists `./src[tree-engine]` before `-e .`,
# so ai-editor-tree-engine is built and installed as a real, NON-editable
# distribution and pip finds `ai-editor-tree-engine==<VERSION>` already
# satisfied instead of reaching for an index that does not carry it yet. The
# aggregate `[tree-engine]` extra is explicit there because the server needs
# every format backend (tree_engine.facade imports the libcst and tree-sitter
# plugins eagerly). WHEN THE NAME IS PUBLISHED: drop `COPY src/ src/` above and
# the `./src[tree-engine]` line from requirements.txt -- nothing else changes,
# because the server already depends on the distribution by name.
RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

# The engine must be importable as an installed distribution, not from /app/src.
# Proves it here, at build time, where a packaging regression is cheap to see.
RUN cd / && python -c "\
import importlib.metadata as m, tree_engine.facade as f; \
print('ai-editor-tree-engine', m.version('ai-editor-tree-engine'), f.__file__); \
assert '/app/src' not in f.__file__, f.__file__"

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
