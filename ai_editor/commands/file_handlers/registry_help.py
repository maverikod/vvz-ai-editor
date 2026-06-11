"""
MCP documentation strings for file handler registry discovery.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

# Appended to MCP descr / schemas so models steer to handler routing vs plain-text pitfalls.
MCP_FILE_MANAGEMENT_REGISTRY_HELP = (
    "Use ``ai_editor.core.file_handlers.registry.get_handler_schema(handler_id, operation)`` "
    "for per-handler request hints and ``list_handler_mappings()`` for suffix→handler rows "
    "(handler ids: text, json, yaml, python). "
    "Legacy **read_project_text_file** / **write_project_text_lines** are compatibility "
    "wrappers — they **must not** be treated as alternate editors for source code "
    "(``.py``, ``.pyi``, …), ``.json``, ``.yaml``, or other structured formats; route those "
    "through universal_file_read, universal_file_save, universal_file_replace, "
    "universal_file_delete, and JSON/YAML/Python/CST tooling as documented."
)

# Compact line for embedding in JSON-schema ``description`` fields (helps MCP help payloads).
REGISTRY_SCHEMA_DISCOVERY_SHORT = (
    "Discovery: ai_editor.core.file_handlers.registry.get_handler_schema(handler_id, operation) "
    "and list_handler_mappings(); handler ids text, json, yaml, python."
)
