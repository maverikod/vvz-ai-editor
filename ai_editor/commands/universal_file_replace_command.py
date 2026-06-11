"""
MCP command: universal_file_replace

Registry-first partial replace: routes by extension before validation, backup, or writes.
Text ranges are validated (including non-overlap) before backup and again in the handler
before any write.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .anchor_check import AnchorMismatch, check_text_anchor
from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from .file_handlers.registry_help import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write
from ..core.exceptions import ValidationError
from ..core.file_handlers.base import (
    VALIDATION_FAILED,
    FileHandlerRequest,
    FileHandlerResult,
)
from ..core.file_handlers.json_handler import JsonFileHandler
from ..core.file_handlers.python_handler import PythonFileHandler
from ..core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ..core.file_handlers.text_handler import (
    TextFileHandler,
    compute_replace_lines_multi,
    compute_replace_lines_single_range,
    persist_plain_text_file_metadata,
)
from ..core.file_handlers.yaml_handler import YamlFileHandler
from ..core.file_lock import file_lock
from ..core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)

# Distinct from JSON null / Python None passed as value for YAML replace
_MISSING_VALUE = object()
TextReplacementTriple = Tuple[int, int, List[str], Optional[str], Optional[str]]


def _sort_text_replacements_bottom_up(
    triples: List[TextReplacementTriple],
) -> List[TextReplacementTriple]:
    """
    Order text replacement ranges for sequential application without line drift.

    Larger physical positions are applied first (bottom of file upward). Within the
    same start_line, larger end_line first. Matches :func:`merge_adjacent_ranges_for_replace`.
    """
    return sorted(triples, key=lambda t: (t[0], t[1]), reverse=True)


def _success_from_handler(fr: FileHandlerResult, *, operation: str) -> SuccessResult:
    data: Dict[str, Any] = {
        "success": True,
        "handler_id": fr.handler_id,
        "operation": operation,
        "file_path": fr.file_path,
        "project_id": fr.project_id,
        "dry_run": fr.dry_run,
        "changed": fr.changed,
    }
    data.update(fr.data)
    return SuccessResult(data=data)


def _error_from_handler(fr: FileHandlerResult) -> ErrorResult:
    return ErrorResult(
        message=fr.message or fr.code,
        code=fr.code or "VALIDATION_FAILED",
        details=fr.details
        or {
            "file_path": fr.file_path,
            "handler_id": fr.handler_id,
            "operation": fr.operation,
        },
    )


def _normalize_text_replacement_triples(
    replacements: List[Any],
) -> Union[List[TextReplacementTriple], str]:
    """Return text replacement triples plus optional anchors, or an error message."""
    out: List[TextReplacementTriple] = []
    for i, item in enumerate(replacements):
        if isinstance(item, dict):
            try:
                a = int(item["start_line"])
                b = int(item["end_line"])
                nl_raw = item["new_lines"]
            except (KeyError, TypeError, ValueError):
                return (
                    f"replacements[{i}] must be an object with "
                    "start_line, end_line, new_lines (list of strings)"
                )
            if not isinstance(nl_raw, list):
                return f"replacements[{i}].new_lines must be a list of strings"
            anchor_head = item.get("anchor_head")
            anchor_tail = item.get("anchor_tail")
            if (anchor_head is None) != (anchor_tail is None):
                return (
                    f"replacements[{i}].anchor_head and anchor_tail must be "
                    "supplied together"
                )
            if anchor_head is not None and not isinstance(anchor_head, str):
                return f"replacements[{i}].anchor_head must be a string"
            if anchor_tail is not None and not isinstance(anchor_tail, str):
                return f"replacements[{i}].anchor_tail must be a string"
            nl = [str(x) for x in nl_raw]
            out.append((a, b, nl, anchor_head, anchor_tail))
        elif isinstance(item, (list, tuple)):
            if len(item) != 3:
                return (
                    f"replacements[{i}] must be [start_line, end_line, new_lines] "
                    "with new_lines as a list of strings"
                )
            try:
                a, b, nl_raw = item[0], item[1], item[2]
                out.append((int(a), int(b), list(nl_raw), None, None))
            except (TypeError, ValueError) as e:
                return f"replacements[{i}]: invalid triple ({e})"
        else:
            return (
                f"replacements[{i}] must be an object or "
                "[start_line, end_line, new_lines] array"
            )
    return out


def _validate_text_replace_local(
    absolute_path: Path,
    extra: Dict[str, Any],
    req: FileHandlerRequest,
) -> Optional[FileHandlerResult]:
    """Mirror TextFileHandler.replace range validation before BackupManager."""
    text = absolute_path.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines(keepends=False)
    multi = extra.get("replacements")
    try:
        if multi is not None:
            triples: List[Tuple[int, int, List[str]]] = []
            for item in multi:
                if not isinstance(item, (list, tuple)) or len(item) != 3:
                    return FileHandlerResult(
                        success=False,
                        handler_id=req.handler_id,
                        operation=req.operation,
                        file_path=req.file_path,
                        project_id=req.project_id,
                        dry_run=req.dry_run,
                        changed=False,
                        message="each replacement must be [start_line, end_line, new_lines]",
                        code=VALIDATION_FAILED,
                    )
                a, b, nl = item[0], item[1], item[2]
                triples.append((int(a), int(b), list(nl)))
            for a, b, anchor_head, anchor_tail in extra.get(
                "replacement_anchor_checks", []
            ):
                check_text_anchor(
                    all_lines,
                    int(a),
                    int(b),
                    anchor_head,
                    anchor_tail,
                )
            compute_replace_lines_multi(all_lines, triples)
        else:
            sl = int(extra["start_line"])
            el = int(extra["end_line"])
            nl = list(extra["new_lines"])
            check_text_anchor(
                all_lines,
                sl,
                el,
                extra.get("anchor_head"),
                extra.get("anchor_tail"),
            )
            compute_replace_lines_single_range(all_lines, sl, el, nl)
    except AnchorMismatch as e:
        return FileHandlerResult(
            success=False,
            handler_id=req.handler_id,
            operation=req.operation,
            file_path=req.file_path,
            project_id=req.project_id,
            dry_run=req.dry_run,
            changed=False,
            message=str(e),
            code="ANCHOR_MISMATCH",
            details=e.details,
        )
    except (ValueError, KeyError, TypeError) as e:
        return FileHandlerResult(
            success=False,
            handler_id=req.handler_id,
            operation=req.operation,
            file_path=req.file_path,
            project_id=req.project_id,
            dry_run=req.dry_run,
            changed=False,
            message=str(e),
            code="INVALID_RANGE",
            details={"reason": str(e)},
        )
    return None


def _validate_replace_payload_for_handler(
    handler_id: str,
    *,
    start_line: Optional[int],
    end_line: Optional[int],
    new_lines: Optional[List[str]],
    replacements: Optional[List[Any]],
    anchor_head: Optional[str],
    anchor_tail: Optional[str],
    anchor_node_id: Optional[str],
    operations: Optional[List[Any]],
    yaml_path: Optional[str],
    value: Any,
    value_provided: bool,
    ops: Optional[List[Any]],
) -> Optional[ErrorResult]:
    has_anchor = (
        anchor_head is not None or anchor_tail is not None or anchor_node_id is not None
    )
    if handler_id != HANDLER_TEXT and has_anchor:
        return ErrorResult(
            message="anchor fields are only supported for text line-range replace",
            code="VALIDATION_ERROR",
            details={
                "handler_id": handler_id,
                "fields": ["anchor_head", "anchor_tail", "anchor_node_id"],
            },
        )

    if handler_id == HANDLER_TEXT:
        if anchor_node_id is not None:
            return ErrorResult(
                message="anchor_node_id is only valid for Python files (.py/.pyi/.pyw)",
                code="VALIDATION_ERROR",
                details={"field": "anchor_node_id"},
            )
        if (anchor_head is None) != (anchor_tail is None):
            return ErrorResult(
                message="anchor_head and anchor_tail must be supplied together",
                code="VALIDATION_ERROR",
                details={"fields": ["anchor_head", "anchor_tail"]},
            )
        if anchor_head is not None and not isinstance(anchor_head, str):
            return ErrorResult(
                message="anchor_head must be a string",
                code="VALIDATION_ERROR",
                details={"field": "anchor_head"},
            )
        if anchor_tail is not None and not isinstance(anchor_tail, str):
            return ErrorResult(
                message="anchor_tail must be a string",
                code="VALIDATION_ERROR",
                details={"field": "anchor_tail"},
            )
        has_single = (
            start_line is not None or end_line is not None or new_lines is not None
        )
        has_multi = replacements is not None
        if has_single and has_multi:
            return ErrorResult(
                message=(
                    "text replace: use either (start_line, end_line, new_lines) "
                    "or replacements, not both"
                ),
                code="VALIDATION_ERROR",
                details={"field": "replacements"},
            )
        if has_multi:
            if not isinstance(replacements, list) or len(replacements) == 0:
                return ErrorResult(
                    message="text replace: replacements must be a non-empty list",
                    code="VALIDATION_ERROR",
                    details={"field": "replacements"},
                )
            err = _normalize_text_replacement_triples(replacements)
            if isinstance(err, str):
                return ErrorResult(
                    message=err,
                    code="VALIDATION_ERROR",
                    details={"field": "replacements"},
                )
            if anchor_head is not None or anchor_tail is not None:
                return ErrorResult(
                    message=(
                        "top-level anchor_head/anchor_tail are only valid for "
                        "single-range text replace; use per-replacement anchors "
                        "with replacements"
                    ),
                    code="VALIDATION_ERROR",
                    details={"fields": ["anchor_head", "anchor_tail"]},
                )
            return None
        if has_single:
            if start_line is None or end_line is None or new_lines is None:
                return ErrorResult(
                    message=(
                        "text replace: start_line, end_line, and new_lines "
                        "are all required for single-range replace"
                    ),
                    code="VALIDATION_ERROR",
                    details={"fields": ["start_line", "end_line", "new_lines"]},
                )
            if not isinstance(new_lines, list):
                return ErrorResult(
                    message="new_lines must be a list of strings",
                    code="VALIDATION_ERROR",
                    details={"field": "new_lines"},
                )
            return None
        return ErrorResult(
            message=(
                "text replace requires either "
                "(start_line, end_line, new_lines) or replacements"
            ),
            code="VALIDATION_ERROR",
            details={"handler_id": HANDLER_TEXT},
        )

    if handler_id == HANDLER_JSON:
        if not isinstance(operations, list) or len(operations) == 0:
            return ErrorResult(
                message="JSON replace requires a non-empty operations list "
                "(json_modify_tree / JSON Pointer style ops)",
                code="VALIDATION_ERROR",
                details={"field": "operations"},
            )
        return None

    if handler_id == HANDLER_YAML:
        if not isinstance(yaml_path, str) or not yaml_path.strip():
            return ErrorResult(
                message="YAML replace requires yaml_path (non-empty JSON Pointer string)",
                code="VALIDATION_ERROR",
                details={"field": "yaml_path"},
            )
        if not value_provided:
            return ErrorResult(
                message="YAML replace requires value (use null to set JSON null)",
                code="VALIDATION_ERROR",
                details={"field": "value"},
            )
        return None

    if handler_id == HANDLER_PYTHON:
        if not isinstance(ops, list) or len(ops) == 0:
            return ErrorResult(
                message="Python replace requires a non-empty ops list "
                "(CST replace-ops; CST-safe only)",
                code="VALIDATION_ERROR",
                details={"field": "ops"},
            )
        return None

    return ErrorResult(
        message=f"Unhandled handler_id for replace validation: {handler_id!r}",
        code="INTERNAL_ERROR",
        details={"handler_id": handler_id},
    )


class UniversalFileReplaceCommand(BaseMCPCommand):
    """Replace regions in project files via handler registry."""

    name = "universal_file_replace"
    version = "1.1.0"
    descr = (
        "Partial replace using the universal handler registry. "
        "Unsupported extensions fail with UNSUPPORTED_FILE_EXTENSION before any backup or write. "
        "Text: single range (start_line, end_line, new_lines) or replacements "
        "(non-overlapping ranges; applied bottom-up so line numbers stay stable). "
        "JSON: operations list. YAML: yaml_path + value. "
        "Python: ops list only. Supports dry_run and diff."
        + " "
        + MCP_FILE_MANAGEMENT_REGISTRY_HELP
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "title": "universal_file_replace",
            "description": (
                "Registry-first replace. Required: project_id, file_path. "
                "Handler-specific: text — (start_line, end_line, new_lines) or "
                "replacements (overlapping ranges rejected; applied bottom-up); json — "
                "operations; yaml — yaml_path, value; python — ops. "
                "Optional: dry_run, diff, backup, commit_message, diff_context_lines, "
                "validate_syntax_only (python), validate_docstrings (python), tree_id (python). "
                + REGISTRY_SCHEMA_DISCOVERY_SHORT
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Single path relative to project root (literal; globs not supported)."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, no write, backup, or DB/index side effects.",
                },
                "diff": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include unified diff when supported.",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), create backups where applicable.",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message for handlers that support it.",
                },
                "diff_context_lines": {
                    "type": "integer",
                    "description": "Optional unified-diff context line count (default 3).",
                },
                "validate_syntax_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Python handler: validate syntax only when applying ops.",
                },
                "validate_docstrings": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Python handler: when False, skip docstring policy checks during validation. "
                        "Use when patching a docstring while pre-existing docstring errors exist "
                        "elsewhere in the same file. Linter and type checker still run."
                    ),
                },
                "tree_id": {
                    "type": "string",
                    "description": "Optional CST tree_id for Python replace.",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Text: single-range replace (with end_line, new_lines).",
                },
                "end_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Text: single-range replace (with start_line, new_lines).",
                },
                "new_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Text: replacement lines for single-range replace.",
                },
                "anchor_head": {
                    "type": "string",
                    "description": (
                        "Text single-range only: first 5 non-whitespace chars "
                        "of the first line in [start_line, end_line]. Server "
                        "rejects the write if actual content differs."
                    ),
                },
                "anchor_tail": {
                    "type": "string",
                    "description": (
                        "Text single-range only: last 5 non-whitespace chars "
                        "of the last line in [start_line, end_line]. Server "
                        "rejects the write if actual content differs."
                    ),
                },
                "anchor_node_id": {
                    "type": "string",
                    "description": (
                        "Python files only: stable_id (UUID4) of the CST node "
                        "at start_line. Mutually exclusive with "
                        "anchor_head/anchor_tail."
                    ),
                },
                "replacements": {
                    "type": "array",
                    "description": (
                        "Text: multiple disjoint ranges. Each item: either "
                        '{"start_line", "end_line", "new_lines", optional '
                        '"anchor_head"/"anchor_tail"} or '
                        "[start_line, end_line, new_lines]. Overlapping ranges rejected. "
                        "Application order is bottom-up (by start_line, then end_line); "
                        "the order of items in this array need not match that order."
                    ),
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "JSON handler: list of json_modify_tree operations "
                        "(JSON Pointer / node addressing per server docs)."
                    ),
                },
                "yaml_path": {
                    "type": "string",
                    "description": (
                        'YAML handler: JSON Pointer path (non-empty; not "" for replace).'
                    ),
                },
                "value": {
                    "description": "YAML handler: new value at yaml_path (any JSON type; null allowed).",
                },
                "ops": {
                    "type": "array",
                    "description": (
                        "Python handler: non-empty CST replace ops (selectors / "
                        "range-safe patches only)."
                    ),
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileReplaceCommand"]) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "detailed_description": cls.descr,
            "registry_discovery_python": (
                "ai_editor.core.file_handlers.registry — get_handler_schema, "
                "list_handler_mappings, HANDLER_IDS"
            ),
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        dry_run: bool = False,
        diff: bool = False,
        backup: bool = True,
        commit_message: Optional[str] = None,
        diff_context_lines: Optional[int] = None,
        validate_syntax_only: bool = False,
        validate_docstrings: bool = True,
        tree_id: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        new_lines: Optional[List[str]] = None,
        anchor_head: Optional[str] = None,
        anchor_tail: Optional[str] = None,
        anchor_node_id: Optional[str] = None,
        replacements: Optional[List[Any]] = None,
        operations: Optional[List[Any]] = None,
        yaml_path: Optional[str] = None,
        value: Any = _MISSING_VALUE,
        ops: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        value_provided = value is not _MISSING_VALUE
        if not value_provided:
            value = None
        try:
            try:
                handler_id = resolve_handler(file_path, "replace")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
                )

            bad = _validate_replace_payload_for_handler(
                handler_id,
                start_line=start_line,
                end_line=end_line,
                new_lines=new_lines,
                replacements=replacements,
                anchor_head=anchor_head,
                anchor_tail=anchor_tail,
                anchor_node_id=anchor_node_id,
                operations=operations,
                yaml_path=yaml_path,
                value=value,
                value_provided=value_provided,
                ops=ops,
            )
            if bad is not None:
                return bad

            absolute_path = self._resolve_file_path_from_project(
                None, project_id, file_path
            )
            root_dir = self._resolve_project_root(project_id)
            database = None

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            if not absolute_path.exists():
                return ErrorResult(
                    message=f"File not found: {absolute_path}",
                    code="FILE_NOT_FOUND",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "handler_id": handler_id,
                        "resolved_path": str(absolute_path),
                    },
                )

            extra: Dict[str, Any] = {"absolute_path": absolute_path}
            if diff_context_lines is not None:
                extra["diff_context_lines"] = diff_context_lines
            if isinstance(commit_message, str) and commit_message.strip():
                extra["commit_message"] = commit_message

            if handler_id == HANDLER_TEXT:
                if replacements is not None:
                    triples = _normalize_text_replacement_triples(replacements)
                    assert isinstance(triples, list)
                    extra["replacement_anchor_checks"] = [
                        (a, b, ah, at)
                        for a, b, _nl, ah, at in triples
                        if ah is not None or at is not None
                    ]
                    ordered = _sort_text_replacements_bottom_up(triples)
                    extra["replacements"] = [
                        [a, b, nl] for a, b, nl, _ah, _at in ordered
                    ]
                else:
                    extra["start_line"] = int(start_line)  # type: ignore[arg-type]
                    extra["end_line"] = int(end_line)  # type: ignore[arg-type]
                    extra["new_lines"] = list(new_lines or [])
                    if anchor_head is not None or anchor_tail is not None:
                        extra["anchor_head"] = anchor_head
                        extra["anchor_tail"] = anchor_tail

            elif handler_id == HANDLER_JSON:
                extra["operations"] = list(operations or [])

            elif handler_id == HANDLER_YAML:
                extra["yaml_path"] = str(yaml_path)
                extra["value"] = value

            elif handler_id == HANDLER_PYTHON:
                extra["root_path"] = root_dir.resolve()
                extra["ops"] = list(ops or [])
                extra["validate_syntax_only"] = validate_syntax_only
                extra["validate_docstrings"] = validate_docstrings
                if tree_id is not None and str(tree_id).strip():
                    extra["tree_id"] = str(tree_id)

            if handler_id in (HANDLER_JSON, HANDLER_YAML):
                extra["database"] = database
                extra["root_dir"] = root_dir.resolve()
                extra["normalized_path"] = normalize_path_simple(str(absolute_path))

            backup_for_handler = bool(backup)
            if handler_id == HANDLER_TEXT and (not dry_run) and backup_for_handler:
                backup_for_handler = False

            req = FileHandlerRequest(
                project_id=project_id,
                file_path=file_path,
                handler_id=handler_id,
                operation="replace",
                dry_run=bool(dry_run),
                diff=bool(diff),
                backup=backup_for_handler,
                extra=extra,
            )

            if handler_id == HANDLER_TEXT:
                fr = self._run_text_replace(
                    req=req,
                    database=database,
                    absolute_path=absolute_path,
                    root_dir=root_dir,
                    backup=bool(backup),
                    dry_run=bool(dry_run),
                )
            elif handler_id == HANDLER_JSON:
                fr = JsonFileHandler().replace(req)
            elif handler_id == HANDLER_YAML:
                fr = YamlFileHandler().replace(req)
            elif handler_id == HANDLER_PYTHON:
                fr = PythonFileHandler().replace(req)
            else:
                return ErrorResult(
                    message=f"Unhandled handler_id after registry resolve: {handler_id!r}",
                    code="INTERNAL_ERROR",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "handler_id": handler_id,
                        "operation": "replace",
                    },
                )

            if not fr.success:
                return _error_from_handler(fr)
            if not dry_run:
                cm = (
                    commit_message.strip()
                    if isinstance(commit_message, str) and commit_message.strip()
                    else None
                )
                git_ok, git_err = commit_after_write(
                    root_dir.resolve(),
                    [absolute_path],
                    "universal_file_replace",
                    commit_message_override=cm,
                    config_data=BaseMCPCommand._get_raw_config(),
                )
                if not git_ok and git_err:
                    logger.warning(
                        "Git commit after universal_file_replace: %s", git_err
                    )
            return _success_from_handler(fr, operation="replace")

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("universal_file_replace failed: %s", e)
            return ErrorResult(
                message=f"universal_file_replace failed: {e}",
                code="UNIVERSAL_FILE_REPLACE_ERROR",
            )

    def _run_text_replace(
        self,
        *,
        req: FileHandlerRequest,
        database: Any,
        absolute_path: Path,
        root_dir: Path,
        backup: bool,
        dry_run: bool,
    ) -> FileHandlerResult:
        """Text replace with BackupManager; files-table metadata after write."""

        def _restore(rel: str, uuid_: str) -> None:
            bm = BackupManager(root_dir)
            bm.restore_file(rel, uuid_)

        with file_lock(absolute_path):
            pre_val = _validate_text_replace_local(absolute_path, req.extra, req)
            if pre_val is not None:
                return pre_val

            normalized_path = normalize_path_simple(str(absolute_path))

            backup_uuid: Optional[str] = None
            if not dry_run and backup and absolute_path.exists():
                bm = BackupManager(root_dir)
                try:
                    rel = str(absolute_path.relative_to(root_dir.resolve()))
                except ValueError:
                    rel = str(absolute_path)
                backup_uuid = bm.create_backup(
                    absolute_path,
                    command="universal_file_replace",
                    comment=f"Before universal_file_replace {req.file_path}",
                )
                if not backup_uuid:
                    return FileHandlerResult(
                        success=False,
                        handler_id=req.handler_id,
                        operation=req.operation,
                        file_path=req.file_path,
                        project_id=req.project_id,
                        dry_run=False,
                        changed=False,
                        message=(
                            "Backup to old_code (versions) is mandatory before write; "
                            "create_backup failed. Aborting universal_file_replace."
                        ),
                        code="BACKUP_REQUIRED",
                        details={
                            "file_path": req.file_path,
                            "resolved_path": str(absolute_path),
                        },
                    )

            fr = TextFileHandler().replace(req)
            if not fr.success:
                return fr

            if dry_run:
                return fr

            meta = persist_plain_text_file_metadata(
                database=database,
                project_id=req.project_id,
                absolute_path=absolute_path,
                normalized_path=normalized_path,
                source_code=absolute_path.read_text(encoding="utf-8", errors="replace"),
            )
            if not meta.get("success"):
                if backup_uuid:
                    try:
                        rel = str(absolute_path.relative_to(root_dir.resolve()))
                    except ValueError:
                        rel = str(absolute_path)
                    _restore(rel, backup_uuid)
                return FileHandlerResult(
                    success=False,
                    handler_id=req.handler_id,
                    operation=req.operation,
                    file_path=req.file_path,
                    project_id=req.project_id,
                    dry_run=False,
                    changed=False,
                    message="Failed to update file metadata: "
                    + str(meta.get("error", "unknown")),
                    code="UPDATE_FILE_DATA_ERROR",
                    details=meta,
                )
            out = dict(fr.data or {})
            out["metadata_update"] = meta
            if backup_uuid:
                out["backup_uuid"] = backup_uuid
            return FileHandlerResult(
                success=True,
                handler_id=fr.handler_id,
                operation=fr.operation,
                file_path=fr.file_path,
                project_id=fr.project_id,
                dry_run=fr.dry_run,
                changed=fr.changed,
                data=out,
            )
