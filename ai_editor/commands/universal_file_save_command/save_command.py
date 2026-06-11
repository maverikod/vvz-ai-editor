"""
MCP command: universal_file_save

Registry-first full-file save: routes by extension to text, JSON, YAML, or Python
handlers. Resolves handler before validation, backup, or writes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ai_editor.commands.base_mcp_command import BaseMCPCommand
from ai_editor.commands.project_text_file_guard import (
    reject_if_write_under_project_venv,
)
from ai_editor.commands.file_handlers.registry_help import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ai_editor.commands.universal_file_save_command.save_helpers import (
    _error_from_handler,
    _success_from_handler,
)
from ai_editor.core.backup_manager import BackupManager
from ai_editor.core.exceptions import ValidationError
from ai_editor.core.file_handlers.base import FileHandlerRequest, FileHandlerResult
from ai_editor.core.file_handlers.json_handler import JsonFileHandler
from ai_editor.core.file_handlers.python_handler import PythonFileHandler
from ai_editor.core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ai_editor.core.file_handlers.text_handler import (
    TextFileHandler,
    persist_plain_text_file_metadata,
)
from ai_editor.core.file_handlers.yaml_handler import YamlFileHandler
from ai_editor.core.file_lock import file_lock
from ai_editor.core.git_integration import commit_after_write
from ai_editor.core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)


class UniversalFileSaveCommand(BaseMCPCommand):
    """Save project files via handler registry (extension routing before side effects)."""

    name = "universal_file_save"

    version = "1.0.0"

    descr = (
        "Full-file save using the universal handler registry. Unsupported extensions fail "
        "with UNSUPPORTED_FILE_EXTENSION before any backup or write. Creates the file when "
        "missing (parent dirs included), then applies the same handler pipeline as overwrite. "
        "Text: full `content` string; JSON/YAML: parseable serialized document; Python: "
        "CST-safe save. Supports dry_run and diff when the handler can serialize before/after."
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
            "title": "universal_file_save",
            "description": (
                "Registry-first save for text, json, yaml, and python handlers. "
                "Required: project_id, file_path, content (string). "
                "Optional: dry_run, diff, backup (default true), create_parent_dirs "
                "(default true, mkdir -p for all handlers), commit_message, "
                "diff_context_lines; validate_syntax_only and tree_id apply only to Python. "
                "Creates missing files and parent directories when allowed; same overwrite "
                "pipelines apply once the file exists. "
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
                        "Single path relative to project root (literal; globs/wildcards not supported). "
                        "May name a file that does not exist yet: all handlers support create with "
                        "create_parent_dirs (mkdir -p). Routing: text (.md, .txt, …), .json, "
                        ".yaml/.yml, .py/.pyi/.pyw — see list_handler_mappings()."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full file body: plain text for .md/.txt/.rst/.adoc; JSON or YAML text "
                        "for .json / .yaml/.yml; Python source for .py/.pyi/.pyw."
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
                    "description": "If true, include unified diff in the response when supported.",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), create backups where the handler does so.",
                },
                "create_parent_dirs": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true (default), create missing parent directories for file_path "
                        "(like mkdir -p) before writing. When false, fail with "
                        "PARENT_DIR_MISSING if a parent directory is absent."
                    ),
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
                "tree_id": {
                    "type": "string",
                    "description": "Optional CST tree_id for Python save path.",
                },
            },
            "required": ["project_id", "file_path", "content"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileSaveCommand"]) -> Dict[str, Any]:
        from .universal_file_save_metadata import get_universal_file_save_metadata

        return get_universal_file_save_metadata(cls)

    @staticmethod
    def _validate_save_payload(content: Optional[str]) -> Optional[ErrorResult]:
        if content is None:
            return ErrorResult(
                message="content is required",
                code="VALIDATION_ERROR",
                details={"field": "content"},
            )
        if not isinstance(content, str):
            return ErrorResult(
                message="content must be a string",
                code="VALIDATION_ERROR",
                details={"field": "content"},
            )
        return None

    async def execute(
        self,
        project_id: str,
        file_path: str,
        content: Optional[str] = None,
        dry_run: bool = False,
        diff: bool = False,
        backup: bool = True,
        commit_message: Optional[str] = None,
        diff_context_lines: Optional[int] = None,
        validate_syntax_only: bool = False,
        tree_id: Optional[str] = None,
        create_parent_dirs: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        try:
            try:
                handler_id = resolve_handler(file_path, "save")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
                )

            bad = self._validate_save_payload(content)
            if bad is not None:
                return bad

            assert content is not None

            absolute_path = self._resolve_file_path_from_project(
                None, project_id, file_path, require_exists=False
            )
            root_dir = self._resolve_project_root(project_id)
            database = None

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            existed_before = absolute_path.exists()

            extra: Dict[str, Any] = {
                "absolute_path": absolute_path,
                "content": content,
                "create_parent_dirs": bool(create_parent_dirs),
            }
            if diff_context_lines is not None:
                extra["diff_context_lines"] = diff_context_lines
            if isinstance(commit_message, str) and commit_message.strip():
                extra["commit_message"] = commit_message

            if handler_id == HANDLER_TEXT:
                backup_for_handler = bool(backup)
                if not dry_run and backup_for_handler:
                    backup_for_handler = False
                req = FileHandlerRequest(
                    project_id=project_id,
                    file_path=file_path,
                    handler_id=handler_id,
                    operation="save",
                    dry_run=bool(dry_run),
                    diff=bool(diff),
                    backup=backup_for_handler,
                    extra=extra,
                )
                fr = self._run_text_save(
                    req=req,
                    database=database,
                    absolute_path=absolute_path,
                    root_dir=root_dir,
                    backup=bool(backup),
                    dry_run=bool(dry_run),
                )
            elif handler_id == HANDLER_JSON:
                extra["database"] = database
                extra["root_dir"] = root_dir.resolve()
                extra["normalized_path"] = normalize_path_simple(str(absolute_path))
                fr = JsonFileHandler().save(
                    FileHandlerRequest(
                        project_id=project_id,
                        file_path=file_path,
                        handler_id=handler_id,
                        operation="save",
                        dry_run=bool(dry_run),
                        diff=bool(diff),
                        backup=bool(backup),
                        extra=extra,
                    )
                )
            elif handler_id == HANDLER_YAML:
                extra["database"] = database
                extra["root_dir"] = root_dir.resolve()
                extra["normalized_path"] = normalize_path_simple(str(absolute_path))
                fr = YamlFileHandler().save(
                    FileHandlerRequest(
                        project_id=project_id,
                        file_path=file_path,
                        handler_id=handler_id,
                        operation="save",
                        dry_run=bool(dry_run),
                        diff=bool(diff),
                        backup=bool(backup),
                        extra=extra,
                    )
                )
            elif handler_id == HANDLER_PYTHON:
                extra["root_path"] = root_dir.resolve()
                extra["database"] = database
                extra["git_command_name"] = "universal_file_save"
                extra["validate_syntax_only"] = bool(validate_syntax_only)
                if tree_id is not None:
                    extra["tree_id"] = tree_id
                if isinstance(commit_message, str) and commit_message.strip():
                    extra["commit_message"] = commit_message.strip()
                fr = PythonFileHandler().save(
                    FileHandlerRequest(
                        project_id=project_id,
                        file_path=file_path,
                        handler_id=handler_id,
                        operation="save",
                        dry_run=bool(dry_run),
                        diff=bool(diff),
                        backup=bool(backup),
                        extra=extra,
                    )
                )
            else:
                return ErrorResult(
                    message=f"Unhandled handler_id after registry resolve: {handler_id!r}",
                    code="INTERNAL_ERROR",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "handler_id": handler_id,
                        "operation": "save",
                    },
                )

            if not fr.success:
                return _error_from_handler(fr)
            if not dry_run and handler_id != HANDLER_PYTHON:
                cm = (
                    commit_message.strip()
                    if isinstance(commit_message, str) and commit_message.strip()
                    else None
                )
                git_ok, git_err = commit_after_write(
                    root_dir.resolve(),
                    [absolute_path],
                    "universal_file_save",
                    commit_message_override=cm,
                    config_data=BaseMCPCommand._get_raw_config(),
                )
                if not git_ok and git_err:
                    logger.warning("Git commit after universal_file_save: %s", git_err)
            result = _success_from_handler(fr, operation="save")
            if isinstance(result, SuccessResult):
                result.data["created"] = not existed_before
            return result

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("universal_file_save failed: %s", e)
            return ErrorResult(
                message=f"universal_file_save failed: {e}",
                code="UNIVERSAL_FILE_SAVE_ERROR",
            )

    def _run_text_save(
        self,
        *,
        req: FileHandlerRequest,
        database: Any,
        absolute_path: Path,
        root_dir: Path,
        backup: bool,
        dry_run: bool,
    ) -> FileHandlerResult:
        """Text save with BackupManager (handler does not) and files-table metadata."""

        def _restore(rel: str, uuid_: str) -> None:
            bm = BackupManager(root_dir)
            bm.restore_file(rel, uuid_)

        with file_lock(
            absolute_path,
            mode="full",
            database=database,
            project_id=req.project_id,
            file_path=req.file_path,
        ):
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
                    command="universal_file_save",
                    comment=f"Before universal_file_save {req.file_path}",
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
                            "create_backup failed. Aborting universal_file_save."
                        ),
                        code="BACKUP_REQUIRED",
                        details={
                            "file_path": req.file_path,
                            "resolved_path": str(absolute_path),
                        },
                    )

            fr = TextFileHandler().save(req)
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
