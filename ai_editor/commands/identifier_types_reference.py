"""
Shared identifier-type reference for command metadata (preview ↔ edit ↔ search).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

# Structural preview / edit (parseable files). Invalid/fallback uses line numbers only.
PREVIEW_NODE_REF_TABLE = (
    "| Extension / path | Preview response `node_ref` | Preview request `node_ref` | Edit target field |\n"
    "|---|---|---|---|\n"
    "| `.py` `.pyi` `.pyw` (marked-tree, default) | **integer** MAP short_id | decimal string, e.g. `\"5\"`; omit for root | "
    "`node_id` / `target_node_id` / …: same int string **or** CST UUID from `universal_file_search` |\n"
    "| `.json` `.yaml` `.yml` (marked-tree, default) | **integer** short_id | decimal string | "
    "`node_ref` / `node_id` / `short_id` int string **or** `json_pointer` |\n"
    "| `.md` (marked-tree, default) | **integer** short_id | decimal string; legacy slug still accepted on edit | "
    "`node_ref` slug (e.g. `intro.setup`) **or** int string from preview |\n"
    "| `.json` `.yaml` legacy tree-temp session | JSON Pointer, e.g. `/timeout` | pointer string | `json_pointer` (+ `value`) |\n"
    "| `.txt` `.rst` `.adoc` | zero-based **line index** string, e.g. `\"3\"` | same | `node_ref` or 1-based `start_line`/`end_line` |\n"
    "| `.jsonl` `.ndjson` | zero-based line index string | same | text line ops (same as `.txt`) |\n"
    "| Parse error / `is_invalid` | `\"\"` (no structural id) | **forbidden** — use `preview_offset` lines | "
    "line-based: `node_ref` `\"\"` + `content`, or `start_line`/`end_line` |\n"
)

PREVIEW_IDENTIFIER_SECTION = (
    "Identifier types (structural mode only):\n"
    f"{PREVIEW_NODE_REF_TABLE}\n"
    "Notes:\n"
    "  - Marked-tree responses serialize `node_ref` as JSON **integer**; requests use **string**.\n"
    "  - `focus.attributes.internal_node_id` (Python) is CST UUID — informational; prefer `node_ref` int.\n"
    "  - `universal_file_search` (Python sidecar only) returns **UUID** `stable_id`/`node_ref`, not MAP short_id.\n"
)

EDIT_IDENTIFIER_SECTION = (
    "Identifier types for operations (match preview or search source):\n"
    f"{PREVIEW_NODE_REF_TABLE}\n"
    "Python sidecar: int short_id from preview is translated to CST UUID before CST edit.\n"
    "JSON/YAML marked-tree: prefer int string in `node_ref`; legacy JSON Pointer still resolves.\n"
    "After `is_invalid` open: only line-based text edits until commit restores structural mode.\n"
)

SEARCH_IDENTIFIER_SECTION = (
    "Search results use **CST stable_id (UUID)** in `matches[].node_ref` and `matches[].stable_id`. "
    "This differs from marked-tree preview, which returns **integer** MAP short_id. "
    "Pass search UUIDs as `node_id` in `universal_file_edit`."
)
