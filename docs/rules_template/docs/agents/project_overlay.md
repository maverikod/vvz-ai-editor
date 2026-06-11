<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Project overlay — `svo_client` (this repository)

Repository-specific paths, behavior, and restrictions. Universal layout: [`PROJECT_RULES.md`](../PROJECT_RULES.md) §3 (`LAYOUT-*`).

## Functional context

- **Role:** Python **client / CLI** for chunking and related services (MCP proxy, HTTP/mTLS examples, local integration scripts).
- **Installable package:** [`svo_client/`](../svo_client/) — public API, CLI, config helpers, errors.
- **Tests:** primary suite under [`tests/`](../tests/) (pytest). Root-level `test_*.py` / `integration_*.py` are legacy runners; **new pytest** tests belong under `tests/`. **Non-pytest** harnesses and ops-style checks → [`scripts/`](../scripts/) per **LAYOUT-07**.
- **API contract reference:** [`docs/openapi.json`](../openapi.json) when aligning client behavior with server shapes.
- **Planning stack (when used):** under `docs/tech_spec/` per hierarchy agents (`tech_spec.md`, `steps/`, `branches/...`).

## Directories and files beyond the universal skeleton

| Path | Note |
|------|------|
| `certs/` | Sample / dev TLS material; do not commit real production private keys. |
| `code_analysis/` | Generated indices when `code_mapper` is run (`USE_CODE_MAP` = yes in [`PROJECT_RULES.md`](../PROJECT_RULES.md) §7). |
| `code_analysis_reports/` | Alternate/older mapper output location — treat as generated; prefer one canonical index path per task. |
| `docs/specs/` | Feature specs and plans (may be large). |
| `docs/bugs/` | Stable / structured bug write-ups (legacy layout allowed). |
| `docs/ai_reports/` | Working AI reports per universal `LAYOUT-06`. |
| `scripts/` | Ops, maintenance, and **non-pytest** runners per universal **LAYOUT-07** (not the pytest tree under `tests/`). |
| Root `*.py` (non-package) | Examples, one-off clients, demos — not part of the `svo_client` package API unless re-exported. |

## Project-specific restrictions

- **Secrets:** Never add real credentials, API keys, or production cert private keys to the repo.
- **Scope:** Changes should stay within **this** repository unless the user explicitly allows touching other paths.
- **Compatibility:** Client behavior may be constrained by **server version**; document breaking assumptions in the relevant spec or PR, not only in code comments.
- **Generated artifacts:** Do not hand-edit `code_analysis/*.yaml` — regenerate via `code_mapper` when required by project rules.

## Filled profile pointer

Concrete profile values for this repo: [`PROJECT_RULES.md`](../PROJECT_RULES.md) **§7**.
