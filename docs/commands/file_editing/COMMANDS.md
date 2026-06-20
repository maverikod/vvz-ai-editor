# File editing — command index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Registered** in thin-server (`hooks_register_part1.py`, `hooks_register_part2.py`):

| Command | Doc | Source |
|---------|-----|--------|
| `health` | — | `ai_editor/commands/health_command.py` |
| **`info`** | [EDITOR_GUIDE.md](EDITOR_GUIDE.md) | `ai_editor/commands/info_command.py` |
| `universal_file_preview` | [universal_file_preview.md](universal_file_preview.md) | `ai_editor/commands/universal_file_preview_command.py` |
| `universal_file_open` | [universal_file_open.md](universal_file_open.md) | `ai_editor/commands/universal_file_edit/open_command.py` |
| `universal_file_edit` | [universal_file_edit.md](universal_file_edit.md) | `ai_editor/commands/universal_file_edit/edit_command.py` |
| `universal_file_write` | [universal_file_write.md](universal_file_write.md) | `ai_editor/commands/universal_file_edit/write_command.py` |
| `universal_file_close` | [universal_file_close.md](universal_file_close.md) | `ai_editor/commands/universal_file_edit/close_command.py` |

**Implemented but not registered** in the current thin server:

| Command | Doc | Note |
|---------|-----|------|
| `universal_file_search` | [universal_file_search.md](universal_file_search.md) | XPath on session CST; use preview drill-down instead |

Cross-cutting: [WORKFLOW.md](WORKFLOW.md), [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md).

Registration: `ai_editor/hooks_register_part1.py` (health, info), `hooks_register_part2.py` (universal_file_*).
