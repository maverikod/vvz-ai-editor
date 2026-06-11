# AI Editor configuration files

| File | Used by |
|------|---------|
| `../config.json` | Local dev (`aiedmgr`, `python -m ai_editor.main`) |
| `ai_editor_container.json` | Docker CMD, Debian package, `docker/run.sh` |

Container config uses paths under `/var/log/ai-editor`, `/var/ai-editor`, and
`/app/mtls_certificates/`. See `docs/CONFIG_LOCAL_VS_CONTAINER.md`.
