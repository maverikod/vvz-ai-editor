<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Rules bundle — copy into a new project

This folder (and `rules_template.zip` in the parent directory) contains a **portable** rules layout for Cursor + shared agent hierarchy docs.

## Contents (directory layout)

```text
rules_template/
  README.md                    ← this file
  docs/
    PROJECT_RULES.md           ← universal IDs + empty §7 table
    projectid.example.json     ← sample if you use CR-003
    agents/
      universal_project_context.md
      common_agent_rules.md
      project_overlay.md       ← stub; replace with your product
      README.md
      MAINTAINERS.md
  .cursor/
    rules/
      project_canonical.mdc
    agents/
      *.md                     ← ten subagent role files (orchestrator / tactical / planner / coder / tester / researchers / doc_writer)
```

## Install (minimal)

1. Copy the **`rules_template/`** tree into the **root** of the target repository (merge with existing `docs/` and `.cursor/`).
2. Or unzip **`rules_template.zip`** at the repository root so paths match the layout above.

## Full adaptation checklist

Do **all** items that apply.

| Step | Action |
|------|--------|
| 1 | Edit **`docs/PROJECT_RULES.md` §0** if any default keys differ for your stack. |
| 2 | Fill **`docs/PROJECT_RULES.md` §7** (same keys as §0, concrete values). |
| 3 | Replace **`docs/agents/project_overlay.md`**: title, functional context, extra directories table, restrictions. |
| 4 | Set **`docs/PROJECT_RULES.md`** header comment (owner / email) if you use it. |
| 5 | If **CR-003** applies: copy `docs/projectid.example.json` to repo-root **`projectid`**, set UUID4 + description, valid JSON only. |
| 6 | Create **`.venv`**, align **`requirements.txt` / `pyproject.toml`** with **CR-007** tools (`black`, `flake8`, `mypy`) or change §0/CR-007 text. Models must follow **CR-005** (verify venv on import/`pip` failures) and **CR-015** (no `--break-system-packages` without explicit user approval of that command). |
| 7 | If you do not use **`code_mapper`**: set `USE_CODE_MAP` to `no` in §7 and remove or ignore `code_analysis/` references. |
| 8 | Trim **`.cursor/agents/*.md`** bodies if your workflow is simpler; **keep** the **Context documents** block at the top of each file. Use **`orchestrator_debug`** + **`orchestrator_tactical_debug`** for small/debug work without `docs/tech_spec/` plans; keep **`orchestrator`** + **`orchestrator_tactical`** for full specs. Orchestrators **do not** work on implementation code directly — see **`docs/agents/common_agent_rules.md` §A16** (tool envelope) and the **`orchestrator` / `orchestrator_tactical`** role files. |
| 9 | In **Cursor → Rules**, add one line pointing to **`docs/PROJECT_RULES.md`** (and enable **`.cursor/rules/project_canonical.mdc`** by keeping it under `.cursor/rules/`). |
| 10 | Optional: copy **`docs/assistant_rules_inventory.md`** from a mature repo if you want MCP / extended §24–§25; update paths from `agents/` links if your layout differs. |
| 11 | Create empty dirs from **LAYOUT-*** if missing: `tests/`, `scripts/`, `logs/`, `configs/`, `docs/ai_reports/` (see **§3**). |

## After merge

- Run your test and lint pipeline once to confirm **CR-007** matches the template.
- Commit the merged tree.

## Regenerating the zip from this repository

1. Copy live rules into the template tree (paths relative to repo root):

```bash
cp -f .cursor/rules/project_canonical.mdc rules_template/.cursor/rules/
cp -f .cursor/agents/*.md rules_template/.cursor/agents/
cp -f docs/agents/common_agent_rules.md docs/agents/README.md docs/agents/project_overlay.md \
      docs/agents/universal_project_context.md docs/agents/MAINTAINERS.md rules_template/docs/agents/
cp -f docs/PROJECT_RULES.md rules_template/docs/
# Optional if your repo keeps a sample next to §0/CR-003:
# cp -f docs/projectid.example.json rules_template/docs/
```

2. From repository root, rebuild the archive:

```bash
zip -r rules_template.zip rules_template -x "rules_template/.git/*"
```

Do **not** use `-x "*.git*"` — it also drops **`scripts/.gitkeep`** and similar tracked placeholders.
