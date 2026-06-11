# Config comparison: local vs container

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Files

| Variant | Config file | Used by |
|---------|-------------|---------|
| Local | `config.json` (project root) | `aiedmgr`, `python -m ai_editor.main` |
| Container | `config/ai_editor_container.json` | Docker CMD, `AI_EDITOR_CONFIG_FILE` |

## Main differences

| Section / key | Local (`config.json`) | Container (`config/ai_editor_container.json`) |
|---------------|----------------------|-----------------------------------------------|
| **server.port** | 15000 | 15000 |
| **server.advertised_host** | host IP | `ai-editor-server` |
| **server.ssl** | `mtls_certificates/mtls_certificates/...` | `/app/mtls_certificates/mtls_certificates/...` |
| **server.log_dir** | `./logs` | `/var/log/ai-editor` |
| **registration** | IP-based proxy URLs | `https://mcp-proxy:3004/...` |
| **ai_editor.database.host** | `192.168.254.26` | same (override in conffile if needed) |
| **ai_editor.storage.editor_workspace_dir** | `data/editor_workspaces` | `/var/ai-editor/editor_workspaces` |
| **file_watcher / worker / docs_indexing** | enabled (local paths) | **disabled** in container |
| **chunker.url** | IP | `svo-chunker` |
| **embedding.host** | IP | `embedding-service` |

PostgreSQL password: set `AI_EDITOR_POSTGRES_PASSWORD` in the container environment
(`docker/container.env.local` for dev, `/etc/default/ai-editor` for production).
