<!--
Tactical task — parent global step: restore_code_analysis_server_registration
-->

# Tactical Task: MCP/mTLS proxy registration and dependent services (vectorizer, chunker)

## Purpose

Establish and verify that `code-analysis-server` is reachable through `mcp-proxy` while the proxy and server use the mTLS material under `mtls_certificates/`, that advertised addresses align with the Docker host context `smart-assistant` (operational mapping: `172.28.0.x` / service DNS names as deployed), and that embedding (vectorizer) and chunker assumptions hold under the same network and TLS model. This task captures repository facts and defines verification; it does not authorize direct work on `test_data/vast_srv`.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/restore_code_analysis_server_registration.md`

## Scope

**Included:** Repository config and entrypoint facts for `mcp-proxy-adapter` wiring, registration keys, server bind/advertise, `code_analysis.chunker` and `code_analysis.embedding` (vectorizer) client settings, `mtls_certificates/` path usage, operational verification via `mcp-proxy` (`list_servers`, `call_server`, `help`).

**Excluded:** Editing `vast_srv` sources or data; changing global `tech_spec.md` or global step files; implementing features unrelated to reachability.

## Boundaries

- Do not modify `test_data/vast_srv` except future campaign work via `tester_ca` through MCP (out of scope here).
- Do not treat local-only process start as success without proxy-mediated proof.

## Dependencies

none

## Parallelization note

May run in parallel with other sibling tactical tasks only if they do not edit the same config files; default is serial with global step 1→2→3.

## Expected outcome

1. Evidence table: config paths, registration URLs, `server_id`, mTLS file paths.
2. Live verification: `mcp-proxy` lists `code-analysis-server`; `call_server` and `help` succeed for at least one command pair.
3. Dependent services: vectorizer (embedding) and chunker reachability validated from the running chain **or** exact blockers documented.

## Correction items

- If committed `config.json` uses `localhost` for embedding/chunker while Docker expects service hostnames, align host fields per deployment (after global approval).
- Resolve `docs/MCP_PROXY_USAGE_GUIDE.md` missing reference from code comments (documentation correction — delegate `doc_writer` if prose is required).

## Questions / escalation rule

Escalate to global orchestrator if `tech_spec.md` must change, if `smart-assistant` addressing cannot be reconciled with committed configs, or if `mcp-proxy-adapter` behavior must be upgraded beyond pinned `requirements.txt`.

---

## Research evidence (from `researcher_code`, consolidated)

- **Wiring:** `code_analysis/main.py`, `main_config.py`, `main_server_config.py` — `mcp_proxy_adapter` `AppFactory`, `ServerEngineFactory`, `build_server_ssl_config`, `SimpleConfig`.
- **Registration keys:** `code_analysis/core/config_validator/field_types.py` — `registration.*`, `registration.ssl.*`; heartbeat URLs in examples.
- **Certs:** Root `config.json` / `config_mtls_proxy.json` — paths under `mtls_certificates/mtls_certificates/` for server, client, registration, embedding, chunker.
- **Server process:** `python -m code_analysis.main` or `python -m code_analysis.cli.server_manager_cli --config <path> start`.
- **Embedding (vectorizer):** `code_analysis/core/svo_client_manager_embedding.py`, `svo_client_manager_config.py` — `code_analysis.embedding` keys: `host`, `port`, `protocol`, `cert_file`, `key_file`, `ca_cert_file`, `check_hostname`, etc.
- **Chunker:** `code_analysis/core/svo_client_manager_chunker.py` — `code_analysis.chunker` keys; mTLS when `protocol` in `("mtls","https")`.
- **Gaps:** Exact POST body for `/register` lives in external `mcp-proxy-adapter` package; no `docker-compose` for `smart-assistant` in repo; `docs/MCP_PROXY_USAGE_GUIDE.md` missing.

---

## File inventory

| action | path | purpose |
|--------|------|---------|
| modify | `config.json` (repo root) | Only if runtime proof shows wrong host/port/registration URL for target network (minimal diff). |
| modify | `config_mtls_proxy.json` | Same, alternate profile. |

*If verification passes without drift, **no** file modifications are required for this task.*

## Class / function inventory

Not applicable — no new or modified Python modules are in scope for this tactical task; optional edits are configuration JSON only.

## Data structures

Not applicable.

## Import map

Not applicable.

## Error handling map

Not applicable at code level; operational verification: failed `call_server` → capture `error` / `message` and record as blocker.

## Config dependency (read/may adjust)

| key | type | notes |
|-----|------|--------|
| `registration.server_id` | string | MCP `server_id`, e.g. `code-analysis-server` |
| `registration.register_url` / `unregister_url` / `registration.heartbeat.url` | string (HTTPS URL) | mTLS client uses `registration.ssl.*` |
| `server.host` / `server.port` / `server.advertised_host` / `server.protocol` | string/int | Listener and advertised OpenAPI base |
| `server.ssl.*` | paths | Server mTLS identity |
| `code_analysis.embedding.*` | mixed | Vectorizer client |
| `code_analysis.chunker.*` | mixed | Chunker client |

## Test plan (verification)

| step | action | pass criterion |
|------|--------|----------------|
| V1 | MCP `list_servers` | `code-analysis-server` present |
| V2 | MCP `call_server` `health` | `success: true`, `proxy_registration.registered: true` |
| V3 | MCP `help` for same server/command | Returns schema/help |
| V4 | MCP `call_server` `check_vectors` with non–`vast_srv` `project_id` | Success implies embedding path usable |
| V5 | Optional: MCP `call_server` on `embedding-service` / `svo-chunker-prod` `health` | Confirms dependents registered to proxy |

## Concrete examples

- **Registration health fragment (expected shape):** `proxy_url` `https://172.28.0.2:3004`, `server_url` `https://172.28.0.1:15000`, `registered: true`.
- **check_vectors (example):** `project_id` = UUID of main `code_analysis` watched project; response includes `vectorization_percentage` and chunk sample metadata.

## Algorithm / logic description (verification)

1. Load parent `tech_spec.md` acceptance criteria.
2. Run MCP discovery and commands in the Test plan table.
3. If any step fails, stop and record exact error payload and suspected config key.
4. If all pass, record C0 satisfied for proxy + dependents in this environment.
5. Do not start editing JSON until a failure implicates a specific key.

## Forbidden approaches

- Declaring success without MCP `list_servers` and `call_server` proof.
- Direct edits under `test_data/vast_srv` for this checkpoint.
- Bypassing `mcp-proxy` for “quick” local curls as a substitute for MCP proof (local debugging may supplement but not replace).

## Read first (for `planner_auto` / `coder_auto`)

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/restore_code_analysis_server_registration.md`
- `docs/REGISTRATION_AND_MTLS.md`
- Root `config.json`, `config_mtls_proxy.json`
