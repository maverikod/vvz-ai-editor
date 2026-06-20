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
| **server.advertised_host** | `${AI_EDITOR_ADVERTISED_HOST}` | `${AI_EDITOR_ADVERTISED_HOST}` |
| **registration** | `${AI_EDITOR_REGISTRATION_HOST}` (+ port env) | same |
| **code_analysis_server.host** | `${AI_EDITOR_CODE_ANALYSIS_HOST}` | `${AI_EDITOR_CODE_ANALYSIS_HOST}` |
| **file_watcher / worker / docs_indexing** | enabled (local paths) | **disabled** in container |
| **chunker.url** | IP | `svo-chunker` |
| **embedding.host** | IP | `embedding-service` |

PostgreSQL password: set `AI_EDITOR_POSTGRES_PASSWORD` in the container environment
(`docker/container.env.local` for dev, `/etc/default/ai-editor` for production).

Network placeholders: set `AI_EDITOR_ADVERTISED_HOST`, `AI_EDITOR_REGISTRATION_HOST`,
`AI_EDITOR_REGISTRATION_PORT` (default 3004), `AI_EDITOR_CODE_ANALYSIS_HOST`, and
`AI_EDITOR_CODE_ANALYSIS_PORT` (default **15010**, not legacy 15001) in `.env` or
container env — see `.env.example`.
