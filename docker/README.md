# Docker Setup for AI Editor

Docker image, local dev scripts, and Debian package (`ai-editor-docker`) for the
AI Editor MCP server.

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Release build (Docker Hub + Debian package)

```bash
export AI_EDITOR_DOCKERHUB_USERNAME=youruser   # optional
export AI_EDITOR_DOCKERHUB_TOKEN=yourtoken     # optional
export AI_EDITOR_DOCKERHUB_REPO=vasilyvz/ai-editor   # optional

./docker/build.sh
```

This will:

1. Build `REPO:VERSION` and `REPO:latest` (VERSION from `pyproject.toml`)
2. Push both tags to Docker Hub (unless `--skip-push`)
3. Create `docker/dist/ai-editor-docker_VERSION_amd64.deb`

Flags: `--skip-push`, `--skip-deb`, `--dev-run`.

### Install on Debian/Ubuntu host

```bash
sudo dpkg -i docker/dist/ai-editor-docker_1.0.7_amd64.deb
sudo apt -f install
ai-editor-info
```

On install the package:

- pulls the matching image from Docker Hub
- creates and starts the `ai-editor` container
- enables `ai-editor-docker.service`

On `apt purge`:

- stops systemd, removes the container and Docker image
- removes `/var/lib/ai-editor` state
- removes log/data/mtls/config parent directories **only when empty of additional files**

Host paths after install:

| Path | Purpose |
|------|---------|
| `/etc/ai-editor/ai_editor_container.json` | Service configuration (conffile) |
| `/etc/ai-editor/mtls_certificates/` | TLS certificates |
| `/var/ai-editor/` | Editor workspaces, versions |
| `/var/ai-editor/editor_workspaces` | CA session workspaces (`ai_editor.storage.workspace_root`) |
| `/var/log/ai-editor/` | Application logs |

```bash
ai-editor-info
sudo ai-editor-docker recreate   # after config or cert changes
```

## Local development

```bash
./docker/build.sh --skip-push --skip-deb --dev-run
```

Or build and run separately:

```bash
./docker/build.sh --skip-push --skip-deb
./docker/run.sh
```

Set `AI_EDITOR_POSTGRES_PASSWORD` in `docker/container.env.local` (not committed).

## Configuration

| Variant | File |
|---------|------|
| Local (project root) | `config.json` |
| Container | `config/ai_editor_container.json` |

Workspace root is configured only via `ai_editor.storage.workspace_root` (C-018).
Local dev `config.json` uses `"data/editor_workspaces"` relative to the config
directory; the Debian/container config uses `"/var/ai-editor/editor_workspaces"`.
The mounted host path must match the value resolved by `resolve_workspace_root`.

See `docs/CONFIG_LOCAL_VS_CONTAINER.md`.

## Port

HTTPS **15000** (host port configurable via `AI_EDITOR_PORT` in `/etc/default/ai-editor`).

## Healthcheck

```bash
curl -fsk https://localhost:15000/health
```
