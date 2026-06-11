# File and Directory Layout Standard

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document defines where files and directories must be placed in the project. Canonical rule source: `.cursorrules`, `.cursor/rules/filestruct.mdc`.

---

## Directory structure

### 📁 scripts/

- **Purpose:** Scripts and test utilities (NOT pytest tests).
- **Contents:** Utility scripts, test scripts (non-pytest), helper scripts, registration scripts.
- **Example:** `register_mcp_server.py`, `test_project_cleanup.py`.

### 📁 docs/

- **Purpose:** All documentation.
- **Contents:** README files, documentation files (.md), API documentation, migration guides, analysis reports.
- **Example:** `README.md`, `COMMANDS_GUIDE.md`, `COMMANDS_INDEX.md`.
- **Layout:** Use the subdirectories below (`reports`, `plans`, `standards`, `commands`, `agents`). Keep `docs/reports/` and `docs/plans/` in the repository even when they contain no documents yet (e.g. track an empty tree with `.gitkeep`) so new analyses and plans are not dropped into the `docs/` root.

### 📁 docs/reports/

- **Purpose:** Analyses and explanations (reports, data-flow and architecture notes).
- **Contents:** Migration guides, analysis reports, technical explanations.
- **Example:** `COMPONENT_INTERACTION.md`, `LOG_WRITE_SITES.md`, `FILE_STRUCTURE_AND_OBJECT_SCHEMA.md`.

### 📁 docs/plans/

- **Purpose:** Technical specifications and plans (TZ, design, step-by-step plans).
- **Contents:** Task descriptions, refactor plans, design docs, implementation steps.
- **Example:** `MUTABLE_CST_LAYER_TASK.md`, `mutable_cst_layer/`, `cst_concept/refactor_plan/`, `design/`.

### 📁 docs/standards/

- **Purpose:** Standards and project rules (logging, drivers, paths, commit rules).
- **Contents:** Standards documents, criteria, format specs.
- **Example:** `DRIVER_STANDARD.md`, `LOG_IMPORTANCE_CRITERIA.md`, `UNIFIED_LOG_FORMAT.md`, `PROJECT_PATH_AND_VENV_RULES.md`, `FILE_AND_DIRECTORY_LAYOUT.md`.

### 📁 docs/commands/

- **Purpose:** Per-command documentation (blocks: ast, backup, code_mapper, code_quality, cst, etc.).
- **Contents:** README.md, COMMANDS.md, one file per command `<command_name>.md`.

### 📁 logs/

- **Purpose:** Server and application logs.
- **Contents:** Application logs, server logs, error logs, access logs.
- **Example:** `mcp_proxy_adapter.log`, `server.log`.

### 📁 data/

- **Purpose:** Data files (databases, data files).
- **Contents:** Database files (.db, .sqlite), data files, test data, configuration data files.
- **Example:** `code_analysis.db`, `test.db`.

### 📁 tests/

- **Purpose:** Pytest tests only.
- **Contents:** Test modules and packages (pytest discovery).

### 📁 code_analysis/

- **Purpose:** Project source code only.
- **Contents:** Python packages and modules, plus generated indices (e.g. method_index.yaml, code_map.yaml) when produced by code_mapper.

### 📁 mtls_certificates/

- **Purpose:** x509 certificates for client connection to foreign services.

### 📁 test_data/

- **Purpose:** Test data for testing; each subdirectory is a separate test project.
- **Contents:** One subdirectory per dataset/project. Each test project subdirectory must have a `projectid` file in its root.

---

## Rules

1. **ALL documentation files (.md) MUST be in `docs/`** (including subdirs: reports, plans, standards, commands).
2. **ALL scripts (non-pytest) MUST be in `scripts/`.**
3. **ALL log files MUST be in `logs/`.**
4. **ALL data files (databases, etc.) MUST be in `data/`.**
5. **Pytest tests MUST remain in `tests/`.**
6. **Source code MUST remain in `code_analysis/`.**

---

## File organization checklist

When adding new files, place them in the correct directory:

| Content type      | Directory        |
|-------------------|-------------------|
| Documentation     | `docs/`           |
| Scripts (non-pytest) | `scripts/`     |
| Logs              | `logs/`           |
| Data / databases  | `data/`           |
| Tests (pytest)    | `tests/`          |
| Source code       | `code_analysis/`  |

Within `docs/`: put analyses and reports in `docs/reports/`, plans and TZ in `docs/plans/`, standards in `docs/standards/`, command docs in `docs/commands/`.
