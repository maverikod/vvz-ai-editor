<!--
Author: Vasiliy Zdanovskiy — vasilyvz@gmail.com
-->

# Project rules

Rule IDs: `CR-*`, `LAYOUT-*`, `NAME-*`. A matching file in `.cursor/agents/*.md` overrides conflicting rows for that role.

---

## Profile (this repository)

| Key | Value | Notes |
|-----|-------|--------|
| `PROJECT_SLUG` | `code_analysis` | Paths and naming. |
| `PRIMARY_LANGUAGE` | `Python` | |
| `PACKAGE_ROOT` | `code_analysis/` | Production code at repo root (no `src/`). |
| `TEST_FRAMEWORK` | `pytest` | Suite under `tests/`. |
| `VENV_DIR` | `.venv` | Must be active for `python` / `pip` / tests / linters (**CR-005**). |
| `CHAT_LOCALE` | `ru` | User-facing chat. |
| `ARTIFACT_LOCALE` | `en` | Code, comments, docstrings, tests, `docs/` unless a doc states otherwise. |
| `HEADER_AUTHOR` | `Vasiliy Zdanovskiy` | File headers (**CR-012**). |
| `HEADER_EMAIL` | `vasilyvz@gmail.com` | |
| `DOC_FILENAME_STYLE` | `snake_case` | New Markdown under `docs/`; legacy names may differ. |
| `USE_CODE_MAP` | `yes` | After structural edits, refresh code-map / indexes (tooling writes under package tree `code_analysis/`). |

**CR-003:** Root [`projectid`](../projectid) (UUID + `description`) must be valid for this repo’s tooling. Watched projects (e.g. under `test_data/`) each have their own `projectid` at project root.

**CR-007 (this repo):** on touched production paths run **`black`**, **`flake8`**, **`mypy`** (see `pytest.ini` / `mypy.ini` / `.flake8`).

---

## 1. Precedence (highest first)

| Rank | Layer |
|------|--------|
| 1 | Current user message. |
| 2 | Safety / repo boundary — **CR-002**. |
| 3 | Active subagent — `.cursor/agents/<name>.md`. |
| 4 | This file — `CR-*`, `LAYOUT-*`, `NAME-*`, Profile. |
| 5 | Tool / IDE defaults. |

---

## 2. Core rules (`CR-*`)

| ID | P | Rule |
|----|---|------|
| **CR-001** | 0 | Execute the current task literally; do not skip stacked instructions. |
| **CR-002** | 0 | Do not modify paths outside this repository without explicit user permission. |
| **CR-003** | 0 | If `projectid` is required: valid JSON with UUID4 `id` + `description`; missing/invalid → stop and report. |
| **CR-004** | 0 | Analysis-only questions → answer in chat; no unsolicited files. Durable docs only when the task asks. |
| **CR-005** | 1 | **Python / venv:** `VENV_DIR` active before `python`, `pip`, tests, linters. On import/`pip` errors, verify interpreter (`which python`, `$VIRTUAL_ENV`), activate, retry. |
| **CR-015** | 0 | No `pip install --break-system-packages` or PEP 668 overrides unless the user explicitly approves that exact command. |
| **CR-006** | 1 | If `USE_CODE_MAP` = yes: after each logically finished structural change, refresh indices (project code-map → under `code_analysis/`). |
| **CR-007** | 1 | After production code changes, run required format/lint/typecheck on touched paths (this repo: `black`, `flake8`, `mypy`). |
| **CR-008** | 1 | Python module size: ~350 lines → prefer split; ≤ ~400 OK; ≥ ~450 → must split. |
| **CR-009** | 1 | Docstrings / types for public API; non-obvious logic: short comments. Abstract API → explicit failure, not silent stubs. CST saves: [docs/standards/PYTHON_DOCSTRING_STANDARD.md](standards/PYTHON_DOCSTRING_STANDARD.md). |
| **CR-010** | 1 | Chat: `CHAT_LOCALE`; artifacts: `ARTIFACT_LOCALE` unless user specifies otherwise. |
| **CR-011** | 2 | Commit after a logical batch; push only when the user asks. |
| **CR-012** | 2 | Headers: `HEADER_AUTHOR` and `HEADER_EMAIL` where the project requires them. |
| **CR-013** | 2 | Imports at top unless lazy-loading is intentional. |
| **CR-014** | 3 | If the project defines log importance (0–10), use it consistently. |
| **CR-016** | 1 | Parallelize independent work when safe; do not serialize without a stated reason. |

**P:** 0 = governance / stop, 1 = quality, 2 = hygiene, 3 = optional.

---

## 3. Repository layout (`LAYOUT-*`)

| ID | Rule |
|----|------|
| **LAYOUT-01** | Production code in **`code_analysis/`** at repository root (no `src/`). |
| **LAYOUT-02** | Tests in **`tests/`** (pytest). |
| **LAYOUT-03** | Logs in **`logs/`**; no secrets in tracked logs. |
| **LAYOUT-04** | Sample / non-secret config patterns in **`configs/`**; secrets not in git. Runtime config may also live at root (e.g. `config.json`) — see overlay. |
| **LAYOUT-05** | Documentation in **`docs/`**. |
| **LAYOUT-06** | Working AI outputs in **`docs/ai_reports/`**; promote finished write-ups into the right `docs/` subtree. |
| **LAYOUT-07** | **`scripts/`** — ops, maintenance, non-pytest harnesses (not the pytest tree). |

```text
<repo>/
  code_analysis/       # package + generated indexes when tooling writes there
  tests/
  scripts/
  logs/
  configs/
  data/
  docs/
    ai_reports/
    agents/
  test_data/           # sample projects; own projectid per subtree
  projectid            # this repo (server/tool)
  .venv/               # local, usually not committed
```

Repo-specific paths and constraints: [`docs/agents/project_overlay.md`](agents/project_overlay.md).

---

## 4. Naming conventions (`NAME-*`)

Python (PEP 8) defaults.

| ID | Scope | Rule |
|----|--------|------|
| **NAME-01** | Modules | `snake_case.py`; one main concept per file. |
| **NAME-02** | Tests | `test_<feature>.py` under `tests/`. |
| **NAME-03** | Packages | Lowercase; multi-word → `snake_case`. |
| **NAME-04** | Classes / exceptions | `PascalCase`; exceptions → `…Error` where idiomatic. |
| **NAME-05** | Functions / methods | `snake_case`; verb-led. |
| **NAME-06** | Variables / params | `snake_case`; no 1–2 char names except loops / math. |
| **NAME-07** | Constants | `UPPER_SNAKE_CASE`. |
| **NAME-08** | Privacy | Leading `_` for internal module API; no trailing `_` except keyword clashes. |
| **NAME-09** | `@property` | `snake_case`; do not duplicate `get_foo()` + `foo` for the same thing. |
| **NAME-10** | Type aliases / TypeVars | `PascalCase` aliases; TypeVar `T`, `T_co`, or descriptive `PascalCase`. |
| **NAME-11** | Enums | Class `PascalCase`; members `UPPER_SNAKE_CASE` if constant-like. |
| **NAME-12** | Markdown filenames | `DOC_FILENAME_STYLE` (`snake_case`). |
| **NAME-13** | Config keys | `snake_case` unless an external schema requires otherwise. |

---

## 5. Anti-patterns (naming & layout)

- Mixed `camelCase` / `snake_case` in public Python APIs without reason.
- Generic names (`data`, `manager`, …) without qualifier.
- Cryptic abbreviations only one author understands.
- Test files not discoverable by pytest (`test_*.py`) unless configured otherwise.

---

## 6. Cursor / agents

- IDE pointer: `.cursor/rules/project_canonical.mdc` → this file and `docs/agents/*`.
- Subagent roles: `.cursor/agents/*.md` with shared rules in `docs/agents/common_agent_rules.md`.
