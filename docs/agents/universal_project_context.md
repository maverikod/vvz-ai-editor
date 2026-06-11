<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Universal project context (reference map)

All universal rules are in **[`docs/PROJECT_RULES.md`](../PROJECT_RULES.md)**:

| Section | Content |
|---------|---------|
| **Profile** | This repository: `PROJECT_SLUG`, `PACKAGE_ROOT`, `VENV_DIR`, locales, `USE_CODE_MAP`, `projectid` (**CR-003**), **CR-007** tools. |
| **1** | Rule precedence. |
| **2** | `CR-*` core rules (**CR-005**, **CR-015**, **CR-016**, …). |
| **3** | `LAYOUT-*` repository layout (includes `code_analysis/`, `test_data/`, …). |
| **4–5** | `NAME-*` naming and anti-patterns. |
| **6** | Cursor / agents pointers. |

Cross-project layout or naming changes belong **only** in `PROJECT_RULES.md`, not in [`project_overlay.md`](project_overlay.md).

Next file for this repo: [`project_overlay.md`](project_overlay.md).
