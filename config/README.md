# AI Editor configuration files

Canonical container template (shipped in pip wheel / Debian package):

| Path | Role |
|------|------|
| `../ai_editor/config_templates/ai_editor_container.json` | **Source of truth** — included in package via `package-data` |

Checkout copy for local Docker bind-mount:

| File | Used by |
|------|---------|
| `ai_editor_container.json` | `docker/run.sh` (mounts `config/` → `/etc/ai-editor`) |

Sync checkout copy from package template:

```bash
python scripts/sync_container_config_template.py
```

| `../config.json` | Local dev (`aiedmgr`, `python -m ai_editor.main`) — generate with `aiedcfg generate` |

Container config uses paths under `/var/log/ai-editor`, `/var/ai-editor`, and
`/app/mtls_certificates/`. Host-specific values use `${AI_EDITOR_*}` placeholders
resolved from `.env` or container environment — see `.env.example`.

See `docs/CONFIG_LOCAL_VS_CONTAINER.md`.
