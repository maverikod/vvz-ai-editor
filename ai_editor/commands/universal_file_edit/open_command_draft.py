"""Format resolution for universal_file_open in workspace mode (C-016, C-008).

Draft/source copies and SessionRepo live in CoreEditSession workspace open;
this module only validates format and collects open metadata (tree_id, fallbacks).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from ai_editor.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    UNKNOWN_FORMAT,
    make_error,
)
from ai_editor.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    draft_path_for_edit_source,
    format_descriptor_from_hint,
    lockfile_path_for_edit_source,
    resolve_format_group_for_edit_source,
)
from ai_editor.commands.universal_file_edit.tree_temp_open_support import (
    acquire_tree_temp_for_open,
)


def resolve_and_create_draft(
    workspace_origin_path: Path,
    workspace_edit_subdir: Path,
    project_id: str,
    format_group_hint: Optional[str] = None,
) -> Union[FormatDescriptor, Dict[str, Any]]:
    """Resolve format group for workspace open; CoreEditSession owns on-disk draft."""
    origin = workspace_origin_path.resolve()
    edit_root = workspace_edit_subdir.resolve()
    edit_source_path = edit_root / origin.name
    try:
        descriptor = resolve_format_group_for_edit_source(edit_source_path)
    except ValueError:
        if format_group_hint:
            try:
                descriptor = format_descriptor_from_hint(format_group_hint, edit_source_path)
            except ValueError:
                return make_error(
                    UNKNOWN_FORMAT,
                    f"Unsupported file type: {origin.suffix!r} (invalid hint: {format_group_hint!r})",
                )
        else:
            return make_error(
                UNKNOWN_FORMAT,
                f"Unsupported file type: {origin.suffix}",
            )
    original_fg = descriptor.format_group
    try:
        tree_id = _prepare_open_metadata(origin, edit_root, descriptor, project_id)
        descriptor.__dict__["tree_id"] = tree_id
    except Exception as exc:
        if original_fg in (FORMAT_TREE_TEMP, FORMAT_SIDECAR):
            try:
                return _text_fallback_descriptor(
                    edit_source_path, original_fg, str(exc)
                )
            except Exception:
                pass
        return make_error(PARSE_ERROR, f"Cannot parse file: {exc}")
    return descriptor


def _text_fallback_descriptor(
    edit_source_path: Path,
    original_fg: str,
    parse_error: str,
) -> FormatDescriptor:
    """Build a text-mode descriptor after parse failure at open."""
    text_descriptor = FormatDescriptor(
        format_group=FORMAT_TEXT,
        handler_id="text",
        draft_path=draft_path_for_edit_source(edit_source_path),
        lockfile_path=lockfile_path_for_edit_source(edit_source_path),
        available_operations=["insert", "delete", "replace"],
    )
    text_descriptor.__dict__["tree_id"] = None
    text_descriptor.__dict__["_fallback_info"] = {
        "fallback_reason": parse_error,
        "original_format_group": original_fg,
    }
    return text_descriptor


def _prepare_open_metadata(
    origin: Path,
    edit_root: Path,
    descriptor: FormatDescriptor,
    project_id: str,
) -> Optional[str]:
    del project_id
    fg = descriptor.format_group
    if fg == FORMAT_SIDECAR:
        return _validate_sidecar_open(origin, edit_root)
    if fg == FORMAT_TREE_TEMP:
        return _prepare_tree_temp_open(origin, edit_root, descriptor)
    if fg == FORMAT_TEXT:
        return None
    raise ValueError(f"Unknown format group: {fg!r}")


def _validate_sidecar_open(origin: Path, edit_root: Path) -> Optional[str]:
    """Parse Python source and register in-memory CST; sidecar is built in edit subdir by core."""
    from ai_editor.core.cst_tree import tree_builder as cst_builder
    from ai_editor.tree.handler_registry import HandlerRegistry

    source_text = origin.read_text(encoding="utf-8")
    HandlerRegistry.default_registry().resolve(origin).parse_content(
        Path(origin.name),
        source_text,
    )
    edit_source = edit_root / origin.name
    tree = cst_builder.create_tree_from_code(
        str(edit_source),
        source_text,
        persist_sidecar=False,
    )
    return str(tree.tree_id)


def _prepare_tree_temp_open(
    origin: Path,
    edit_root: Path,
    descriptor: FormatDescriptor,
) -> Optional[str]:
    raw_bytes = origin.read_bytes()
    acq = acquire_tree_temp_for_open(
        project_root=edit_root,
        source_abs=origin,
        handler_id=descriptor.handler_id,
        raw_source_bytes=raw_bytes,
        workspace_origin_path=origin,
        workspace_edit_root=edit_root,
    )
    descriptor.__dict__["_tree_temp_session_kwargs"] = {
        "tree_id": None,
        "source_sha256_at_open": acq.source_sha256,
        "tree_temp_roots": acq.roots,
        "sidecar_write_intent": acq.sidecar_write_intent.value,
    }
    return None
