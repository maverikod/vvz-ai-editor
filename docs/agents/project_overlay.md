<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Project overlay — `code_analysis` (this repository)

Repository-specific paths, behavior, and restrictions. Universal layout: [`PROJECT_RULES.md`](../PROJECT_RULES.md) section 3 (`LAYOUT-*`).

## Functional context

- **Role:** **Code analysis server** — OpenAPI/MCP surface for CST-based Python edits, indexes, search, formatting, linting, and project registration over watched directories.
- **Installable package:** [`code_analysis/`](../../code_analysis/) — server, command handlers, DB, workers, CLI (`code_analysis.cli.*`).
- **Tests:** pytest under [`tests/`](../../tests/). **Non-pytest** harnesses, smoke runners, and ops scripts → [`scripts/`](../../scripts/) per **LAYOUT-07**.
- **Configuration:** Primary runtime config at repo root [`config.json`](../../config.json) (and variants such as `config_mtls_proxy.json`); sample schemas live under [`docs/`](../). **LAYOUT-04** directory [`configs/`](../../configs/) holds sample / non-secret configuration patterns when added.
- **Planning stack (when used):** under `docs/plans/` or `docs/tech_spec/` per agent hierarchy, consistent with [`common_agent_rules.md`](common_agent_rules.md).
- **Runtime dependency:** `mcp-proxy-adapter>=8.10.13` (help merges `get_schema()` + `metadata()` per [`standards/METADATA_SCHEMA_STANDARD.md`](../standards/METADATA_SCHEMA_STANDARD.md)).

## Directories and files beyond the universal skeleton

| Path | Note |
|------|------|
| `data/` | SQLite and other local data stores (see `.cursorrules` / project standards). |
| `logs/` | Server and application logs. |
| `test_data/` | Nested sample projects; each subtree may have its own `projectid`. **Agent rule:** code under `test_data/` is read/written only via this project’s server (MCP), not direct file tools — see `.cursor/rules/test-data.mdc` and `docs/TEST_DATA_AI_RULES.md`. |
| `mtls_certificates/` | Dev/proxy TLS material; do not commit production private keys. |
| `old_code/` / `backups/` | Versioned backups from the server’s backup manager; treat as generated or operational. |
| `code_analysis/` (package) | Production code **and** generated code-map artifacts when the tool writes under the package tree (`USE_CODE_MAP` = yes — see [`PROJECT_RULES.md`](../PROJECT_RULES.md) Profile). |
| `docs/commands/` | Command reference for the server API. |
| `docs/plans/`, `docs/reports/`, `docs/standards/` | Design, reports, and standards per existing repo layout. Command schema/metadata: [`docs/standards/METADATA_SCHEMA_STANDARD.md`](../standards/METADATA_SCHEMA_STANDARD.md). |
| `docs/ai_reports/` | Working AI outputs per **LAYOUT-06** (create/promote as needed). |
| `.cursor/rules/` | IDE rules (`project_canonical.mdc`, `test-data.mdc`, `filestruct.mdc`, …). |

## Project-specific restrictions

- **Secrets:** Do not commit real API keys, passwords, or production private keys.
- **Scope:** Stay inside this repository unless the user explicitly allows other paths (**CR-002**).
- **Testing the server:** Prefer MCP proxy tools for command verification when project rules require it (see `.cursorrules`).
- **Generated / backup trees:** Do not hand-edit indexed or backup copies as the source of truth; regenerate or edit through the supported tooling.

## Filled profile pointer

Profile (keys and values for this repo): [`PROJECT_RULES.md`](../PROJECT_RULES.md#profile-this-repository).
