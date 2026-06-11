"""
YAML file handler: structured load/edit/save via stable path addressing.

Uses PyYAML (``yaml.safe_load`` / ``yaml.safe_dump``). **Comments, block style,
and anchors are not preserved** on round-trip; PyYAML drops them when parsing
to native Python structures. Use a round-trip-aware library if comment fidelity
is required.

**Path syntax (``yaml_path``):** JSON Pointer (RFC 6901) over the loaded
document, after ``yaml.safe_load``:

- ``""`` (empty string) addresses the **root** value.
- Any non-empty path **must** start with ``/``. Reference tokens are separated
  by ``/``. Within a token, ``~1`` encodes ``/`` and ``~0`` encodes ``~``.
- For a **mapping**, a token is the string key (after unescaping).
- For a **sequence**, a token must be a decimal array index without unnecessary
  leading zeros (``0``–``9``, ``10``, …); indices are **0-based**.

Plain-text line-based keys (``start_line``, ``end_line``, …) are rejected;
use ``yaml_path`` (and ``value`` for replace) instead.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..backup_manager import BackupManager
from .base import (
    VALIDATION_FAILED,
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    standard_error_result,
)
from .diff_support import diff_data_for_text_mutation
from .path_utils import ensure_parent_directories
from .registry import HANDLER_YAML, get_handler_schema
from .text_handler import (
    diff_context_lines_from_extra,
    persist_plain_text_file_metadata,
)

YAML_SUFFIXES = frozenset({".yaml", ".yml"})

LINE_RANGE_EXTRA_KEYS = frozenset(
    {"start_line", "end_line", "new_lines", "replacements"}
)

_ARRAY_INDEX_RE = re.compile(r"^(0|[1-9][0-9]*)$")


def ensure_yaml_suffix(file_path: str) -> None:
    suf = Path(file_path).suffix.lower()
    if suf not in YAML_SUFFIXES:
        raise ValueError(f"Not a configured YAML suffix: {suf!r}")


def is_registered_yaml_suffix(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in YAML_SUFFIXES


def _reject_line_range_params(
    extra: Dict[str, Any], *, request: FileHandlerRequest
) -> Optional[FileHandlerResult]:
    overlap = LINE_RANGE_EXTRA_KEYS.intersection(extra.keys())
    if not overlap:
        return None
    return standard_error_result(
        code=VALIDATION_FAILED,
        message=(
            "YAML files use yaml_path (JSON Pointer) for edits, not plain-text "
            f"line ranges (remove: {sorted(overlap)})"
        ),
        request=request,
        extra_details={"unsupported_keys": sorted(overlap)},
    )


def _require_path_extra(request: FileHandlerRequest) -> Path | FileHandlerResult:
    abs_path = request.extra.get("absolute_path")
    if not isinstance(abs_path, Path):
        return standard_error_result(
            code=VALIDATION_FAILED,
            message="extra.absolute_path (Path) is required",
            request=request,
        )
    try:
        ensure_yaml_suffix(str(abs_path))
    except ValueError as e:
        return standard_error_result(
            code=VALIDATION_FAILED,
            message=str(e),
            request=request,
        )
    return abs_path


def parse_yaml_path(yaml_path: str) -> List[str]:
    """
    Parse ``yaml_path`` into JSON Pointer reference tokens (root → leaf).

    Raises:
        ValueError: if the string is not a valid pointer for this handler.
    """
    if yaml_path == "":
        return []
    if not yaml_path.startswith("/"):
        raise ValueError(
            "yaml_path must be '' (root) or a JSON Pointer starting with '/'"
        )
    if yaml_path == "/":
        return [""]
    segments = yaml_path[1:].split("/")
    tokens: List[str] = []
    for seg in segments:
        tok = seg.replace("~1", "/").replace("~0", "~")
        tokens.append(tok)
    return tokens


def _navigate_parent(root: Any, tokens: List[str]) -> Tuple[Any, str, List[Any]]:
    """
    Walk ``tokens`` except the last; return (parent, last_token, chain).

    ``chain`` is [root, child1, ... parent] for existence checks.
    """
    if not tokens:
        raise ValueError(
            "cannot navigate parent for empty path (use root ops explicitly)"
        )
    chain: List[Any] = [root]
    cur = root
    for tok in tokens[:-1]:
        if isinstance(cur, dict):
            if tok not in cur:
                raise KeyError(f"missing key {tok!r} along yaml_path")
            cur = cur[tok]
        elif isinstance(cur, list):
            if not _ARRAY_INDEX_RE.match(tok):
                raise TypeError(
                    f"expected numeric index at {tok!r} inside a sequence, got {type(cur)}"
                )
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                raise IndexError(f"list index {idx} out of range")
            cur = cur[idx]
        else:
            raise TypeError(
                f"cannot descend into non-collection at token {tok!r} ({type(cur).__name__})"
            )
        chain.append(cur)
    return cur, tokens[-1], chain


def _navigate_parent_for_set(root: Any, tokens: List[str]) -> Tuple[Any, str]:
    """Like strict navigation but creates missing mapping keys as empty dicts."""
    if not tokens:
        raise ValueError(
            "cannot navigate parent for empty path (use root ops explicitly)"
        )
    cur = root
    for tok in tokens[:-1]:
        if isinstance(cur, dict):
            if tok not in cur:
                cur[tok] = {}
            cur = cur[tok]
        elif isinstance(cur, list):
            if not _ARRAY_INDEX_RE.match(tok):
                raise TypeError(
                    f"expected numeric index at {tok!r} inside a sequence, got {type(cur)}"
                )
            idx = int(tok)
            if idx < 0 or idx >= len(cur):
                raise IndexError(f"list index {idx} out of range")
            cur = cur[idx]
        else:
            raise TypeError(
                f"cannot descend into non-collection at token {tok!r} ({type(cur).__name__})"
            )
    return cur, tokens[-1]


def get_at_path(root: Any, yaml_path: str) -> Any:
    """Return value at ``yaml_path``; raises if path is invalid or missing."""
    tokens = parse_yaml_path(yaml_path)
    if not tokens:
        return root
    parent, last, _ = _navigate_parent(root, tokens)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f"no key {last!r} at path")
        return parent[last]
    if isinstance(parent, list):
        if not _ARRAY_INDEX_RE.match(last):
            raise TypeError(f"invalid list index token {last!r}")
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError(f"list index {idx} out of range")
        return parent[idx]
    raise TypeError(f"cannot index into {type(parent).__name__}")


def set_at_path(root: Any, yaml_path: str, value: Any) -> None:
    """
    Set value at ``yaml_path``. Creates missing **mapping** keys along the path;
    does not auto-create lists. Root path ``""`` replaces the caller's root
    reference only if the caller assigns the result — this mutates document
    tree in place for non-root paths.
    """
    tokens = parse_yaml_path(yaml_path)
    if not tokens:
        raise ValueError("use save() to replace the full document root")
    parent, last = _navigate_parent_for_set(root, tokens)
    if isinstance(parent, dict):
        parent[last] = value
        return
    if isinstance(parent, list):
        if not _ARRAY_INDEX_RE.match(last):
            raise TypeError(f"invalid list index token {last!r}")
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError(f"list index {idx} out of range")
        parent[idx] = value
        return
    raise TypeError(f"cannot assign into {type(parent).__name__}")


def delete_at_path(root: Any, yaml_path: str) -> None:
    """Remove key or list element at ``yaml_path``. Root ``""`` may not be deleted."""
    tokens = parse_yaml_path(yaml_path)
    if not tokens:
        raise ValueError("cannot delete root with yaml_path; use delete_full_file")
    parent, last, _ = _navigate_parent(root, tokens)
    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f"no key {last!r} at path")
        del parent[last]
        return
    if isinstance(parent, list):
        if not _ARRAY_INDEX_RE.match(last):
            raise TypeError(f"invalid list index token {last!r}")
        idx = int(last)
        if idx < 0 or idx >= len(parent):
            raise IndexError(f"list index {idx} out of range")
        parent.pop(idx)
        return
    raise TypeError(f"cannot delete from {type(parent).__name__}")


def _serialize_document(data: Any) -> str:
    """Deterministic UTF-8 text for diff/save (no comments preserved)."""
    return yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


def _load_yaml_document(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e


def _collect_paths(value: Any, prefix: str) -> List[str]:
    """All JSON Pointer paths to nodes (root included as '')."""
    paths: List[str] = [prefix]
    if isinstance(value, dict):
        for k in sorted(value.keys(), key=lambda x: str(x)):
            escaped = str(k).replace("~", "~0").replace("/", "~1")
            p = f"{prefix}/{escaped}" if prefix else f"/{escaped}"
            paths.extend(_collect_paths(value[k], p))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            p = f"{prefix}/{i}" if prefix else f"/{i}"
            paths.extend(_collect_paths(item, p))
    return paths


class YamlFileHandler(BaseFileHandler):
    """
    Structured YAML: ``read`` returns parsed ``document`` and path metadata;
    ``save`` / ``replace`` / ``delete`` use ``yaml_path`` (JSON Pointer) and
    ``BackupManager`` for existing files when ``backup`` is true.
    """

    @property
    def handler_id(self) -> str:
        return HANDLER_YAML

    def json_schema_for(self, operation: str) -> Dict[str, Any]:
        return get_handler_schema(HANDLER_YAML, operation)

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        raw = abs_path.read_text(encoding="utf-8")
        try:
            data = _load_yaml_document(raw)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )

        paths = _collect_paths(data, "") if data is not None else [""]
        return FileHandlerResult(
            success=True,
            handler_id=self.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=request.dry_run,
            changed=False,
            data={
                "document": data,
                "paths": paths,
                "path_syntax": (
                    "JSON Pointer (RFC 6901): '' = root; /a/0/b = root['a'][0]['b']; "
                    "~0 ~1 escapes"
                ),
                "total_paths": len(paths),
            },
        )

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        content = request.extra.get("content")
        if not isinstance(content, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.content (str) is required for YAML save",
                request=request,
            )
        try:
            data = _load_yaml_document(content)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )

        label = Path(request.file_path).name
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        ctx = diff_context_lines_from_extra(request.extra)

        before_text = ""
        if abs_path.exists():
            before_text = abs_path.read_text(encoding="utf-8")
        after_text = _serialize_document(data)

        changed = before_text != after_text
        diff_payload = diff_data_for_text_mutation(
            before_text,
            after_text,
            include_diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=changed,
                data={
                    **diff_payload,
                    "would_change": changed,
                    "would_create": not abs_path.exists(),
                    "serialized": after_text,
                },
            )

        create_parent_dirs = bool(request.extra.get("create_parent_dirs", True))
        parent_err = ensure_parent_directories(
            abs_path, create_parent_dirs=create_parent_dirs
        )
        if parent_err:
            return standard_error_result(
                code="PARENT_DIR_MISSING",
                message=parent_err,
                request=request,
            )

        root_dir = request.extra.get("root_dir")
        if not isinstance(root_dir, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.root_dir (Path) is required for YAML save (backup path)",
                request=request,
            )
        root_dir = root_dir.resolve()

        if abs_path.exists() and request.backup:
            bm = BackupManager(root_dir)
            uuid_ = bm.create_backup(
                abs_path.resolve(),
                command="yaml_handler_save",
                comment=f"Before save {request.file_path}",
            )
            if not uuid_:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="create_backup failed; refusing to write without backup",
                    request=request,
                )

        abs_path.write_text(after_text, encoding="utf-8")

        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        db = request.extra.get("database")
        if db is not None:
            norm = request.extra.get("normalized_path")
            if isinstance(norm, str) and norm.strip():
                meta = persist_plain_text_file_metadata(
                    db,
                    request.project_id,
                    abs_path.resolve(),
                    norm.strip(),
                    after_text,
                )
                out_data["metadata_result"] = meta
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=changed,
            data=out_data,
        )

    def replace(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        ypath = request.extra.get("yaml_path")
        if not isinstance(ypath, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.yaml_path (str) is required for YAML replace",
                request=request,
            )
        try:
            parse_yaml_path(ypath)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
                extra_details={"yaml_path": ypath},
            )
        if ypath == "":
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.yaml_path must not be empty for replace; use save() for full file",
                request=request,
            )

        if "value" not in request.extra:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.value is required for YAML replace",
                request=request,
            )
        value = request.extra["value"]

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        before_text = abs_path.read_text(encoding="utf-8")
        try:
            doc = _load_yaml_document(before_text)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )
        if doc is None:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="cannot replace into empty document (null root)",
                request=request,
            )

        doc_copy = copy.deepcopy(doc)
        try:
            set_at_path(doc_copy, ypath, copy.deepcopy(value))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"invalid yaml_path: {e}",
                request=request,
                extra_details={"yaml_path": ypath, "error": str(e)},
            )

        after_text = _serialize_document(doc_copy)
        changed = before_text != after_text

        label = Path(request.file_path).name
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        ctx = diff_context_lines_from_extra(request.extra)
        diff_payload = diff_data_for_text_mutation(
            before_text,
            after_text,
            include_diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=changed,
                data={
                    **diff_payload,
                    "would_change": changed,
                    "serialized": after_text,
                },
            )

        root_dir = request.extra.get("root_dir")
        if not isinstance(root_dir, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.root_dir (Path) is required for YAML replace (backup path)",
                request=request,
            )
        root_dir = root_dir.resolve()

        if request.backup:
            bm = BackupManager(root_dir)
            uuid_ = bm.create_backup(
                abs_path.resolve(),
                command="yaml_handler_replace",
                comment=f"Before replace {request.file_path}",
            )
            if not uuid_:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="create_backup failed; refusing to write without backup",
                    request=request,
                )

        abs_path.write_text(after_text, encoding="utf-8")

        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        db = request.extra.get("database")
        if db is not None:
            norm = request.extra.get("normalized_path")
            if isinstance(norm, str) and norm.strip():
                meta = persist_plain_text_file_metadata(
                    db,
                    request.project_id,
                    abs_path.resolve(),
                    norm.strip(),
                    after_text,
                )
                out_data["metadata_result"] = meta
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=changed,
            data=out_data,
        )

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        pre = self.mutating_precheck(request)
        if pre is not None:
            return pre

        bad = _reject_line_range_params(request.extra, request=request)
        if bad is not None:
            return bad

        abs_ex = _require_path_extra(request)
        if isinstance(abs_ex, FileHandlerResult):
            return abs_ex
        abs_path = abs_ex

        delete_full = bool(request.extra.get("delete_full_file"))

        if delete_full:
            root_dir = request.extra.get("root_dir")
            if not isinstance(root_dir, Path):
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="extra.root_dir (Path) is required for YAML delete_full_file",
                    request=request,
                )
            root_dir = root_dir.resolve()

            if request.dry_run:
                return FileHandlerResult(
                    success=True,
                    handler_id=request.handler_id,
                    operation=request.operation,
                    file_path=request.file_path,
                    project_id=request.project_id,
                    dry_run=True,
                    changed=abs_path.exists(),
                    data={"would_delete_file": True},
                )

            if not abs_path.exists():
                return FileHandlerResult(
                    success=True,
                    handler_id=request.handler_id,
                    operation=request.operation,
                    file_path=request.file_path,
                    project_id=request.project_id,
                    dry_run=False,
                    changed=False,
                    data={"deleted_file": False},
                )

            backup_uuid: Optional[str] = None
            if request.backup:
                bm = BackupManager(root_dir)
                backup_uuid = bm.create_backup(
                    abs_path.resolve(),
                    command="yaml_handler_delete",
                    comment=f"Before delete {request.file_path}",
                )
                if not backup_uuid:
                    return standard_error_result(
                        code=VALIDATION_FAILED,
                        message="create_backup failed; refusing to delete without backup",
                        request=request,
                    )

            abs_path.unlink()
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=False,
                changed=True,
                data={"deleted_file": True, "backup_uuid": backup_uuid},
            )

        ypath = request.extra.get("yaml_path")
        if not isinstance(ypath, str):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=(
                    "YAML delete requires delete_full_file or extra.yaml_path "
                    "(JSON Pointer)"
                ),
                request=request,
            )
        try:
            parse_yaml_path(ypath)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
                extra_details={"yaml_path": ypath},
            )
        if ypath == "":
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.yaml_path must not be empty; use delete_full_file for file removal",
                request=request,
            )

        if not abs_path.exists():
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"File not found: {abs_path}",
                request=request,
            )

        before_text = abs_path.read_text(encoding="utf-8")
        try:
            doc = _load_yaml_document(before_text)
        except ValueError as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=str(e),
                request=request,
            )
        if doc is None:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="cannot delete from empty document (null root)",
                request=request,
            )

        doc_copy = copy.deepcopy(doc)
        try:
            delete_at_path(doc_copy, ypath)
        except (ValueError, KeyError, IndexError, TypeError) as e:
            return standard_error_result(
                code=VALIDATION_FAILED,
                message=f"invalid yaml_path: {e}",
                request=request,
                extra_details={"yaml_path": ypath, "error": str(e)},
            )

        after_text = _serialize_document(doc_copy)
        changed = before_text != after_text

        label = Path(request.file_path).name
        lbl_a = f"a/{label}"
        lbl_b = f"b/{label}"
        ctx = diff_context_lines_from_extra(request.extra)
        diff_payload = diff_data_for_text_mutation(
            before_text,
            after_text,
            include_diff=bool(request.diff),
            before_label=lbl_a,
            after_label=lbl_b,
            context_lines=ctx,
        )

        if request.dry_run:
            return FileHandlerResult(
                success=True,
                handler_id=request.handler_id,
                operation=request.operation,
                file_path=request.file_path,
                project_id=request.project_id,
                dry_run=True,
                changed=changed,
                data={
                    **diff_payload,
                    "would_change": changed,
                    "serialized": after_text,
                },
            )

        root_dir = request.extra.get("root_dir")
        if not isinstance(root_dir, Path):
            return standard_error_result(
                code=VALIDATION_FAILED,
                message="extra.root_dir (Path) is required for YAML path delete (backup path)",
                request=request,
            )
        root_dir = root_dir.resolve()

        if request.backup:
            bm = BackupManager(root_dir)
            uuid_ = bm.create_backup(
                abs_path.resolve(),
                command="yaml_handler_delete_path",
                comment=f"Before delete path {request.file_path}",
            )
            if not uuid_:
                return standard_error_result(
                    code=VALIDATION_FAILED,
                    message="create_backup failed; refusing to write without backup",
                    request=request,
                )

        abs_path.write_text(after_text, encoding="utf-8")

        out_data: Dict[str, Any] = (
            dict(diff_payload)
            if request.diff
            else {"diff": "", "changed_line_ranges": []}
        )
        db = request.extra.get("database")
        if db is not None:
            norm = request.extra.get("normalized_path")
            if isinstance(norm, str) and norm.strip():
                meta = persist_plain_text_file_metadata(
                    db,
                    request.project_id,
                    abs_path.resolve(),
                    norm.strip(),
                    after_text,
                )
                out_data["metadata_result"] = meta
        return FileHandlerResult(
            success=True,
            handler_id=request.handler_id,
            operation=request.operation,
            file_path=request.file_path,
            project_id=request.project_id,
            dry_run=False,
            changed=changed,
            data=out_data,
        )
