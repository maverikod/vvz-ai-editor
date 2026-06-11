"""
Parse code snippets into CST statements for tree modifier operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional, Union, cast

import libcst as cst

if TYPE_CHECKING:
    from .models import CSTTree

_SNIPPET_CLASS_NAME = "__ca_snippet_ctx__"
_SNIPPET_FUNC_NAME = "__ca_snippet_ctx__"

# Node types for replace/delete that resolve by exact span (no promotion to
# enclosing Module/IndentedBlock statement).
FINE_GRAINED_REPLACE_NODE_TYPES = frozenset({"Annotation", "Name", "Param"})


def replacement_text_includes_decorators(code: str) -> bool:
    """True when the first non-empty line of replacement text is a decorator."""
    for line in code.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.startswith("@")
    return False


def class_or_function_snippet_needs_full_replace(code: str) -> bool:
    """
    True when replacement text for a ClassDef/FunctionDef includes a body
    (must use full replace_node), not header-only (_replace_node_header).
    """
    lines = code.splitlines()
    if len([ln for ln in lines if ln.strip()]) > 1:
        return True
    return any(
        i > 0 and (ln.startswith((" ", "\t")) or not ln.strip())
        for i, ln in enumerate(lines)
    )


def join_code_lines(lines: List[str]) -> str:
    """Join ``code_lines`` into one string without double newlines.

    Elements may include a trailing ``\\n`` (standard convention) or be bare
    lines without a newline. Trailing newlines are stripped before joining.
    """
    if not lines:
        return ""
    return "\n".join(str(line).rstrip("\n") for line in lines)


def _snippet_as_string(code: Optional[str], code_lines: Optional[List[str]]) -> str:
    if code_lines is not None:
        if code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        return join_code_lines(code_lines)
    if code is None:
        return ""
    return code


def parse_param_snippet(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> cst.Param:
    """
    Parse a single function parameter (e.g. ``self``, ``x: int``, ``*args``)
    for leaf Param replacement.
    """
    raw = _snippet_as_string(code, code_lines)
    if not raw.strip():
        raise ValueError("Param replacement code is empty")
    normalized = _normalize_snippet_indentation(raw)
    wrapped = f"def __leaf_param__({normalized.strip()}): pass\n"
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as e:
        raise ValueError(f"Invalid parameter syntax: {e}") from e
    if not mod.body or not isinstance(mod.body[0], cst.FunctionDef):
        raise ValueError("Param snippet did not parse as a function parameter list")
    fd = mod.body[0]
    params = fd.params
    collected: List[cst.Param] = list(params.params)
    if params.star_arg and isinstance(params.star_arg, cst.Param):
        collected.append(params.star_arg)
    if params.kwonly_params:
        collected.extend(params.kwonly_params)
    if params.star_kwarg:
        collected.append(params.star_kwarg)
    if len(collected) != 1:
        raise ValueError(
            "Param replacement must expand to exactly one parameter; "
            f"got {len(collected)}"
        )
    return collected[0]


def parse_annotation_snippet(
    code: Optional[str] = None,
    code_lines: Optional[List[str]] = None,
) -> cst.Annotation:
    """Parse a parameter or return annotation snippet for leaf Annotation replacement."""
    raw = _snippet_as_string(code, code_lines)
    if not raw.strip():
        raise ValueError("Annotation replacement code is empty")
    normalized = _normalize_snippet_indentation(raw)
    text = normalized.strip()
    if text.startswith("->"):
        wrapped = f"def __ann_return__(){text}:\n    pass\n"
        try:
            mod = cst.parse_module(wrapped)
        except cst.ParserSyntaxError as e:
            raise ValueError(f"Invalid return annotation syntax: {e}") from e
        if not mod.body or not isinstance(mod.body[0], cst.FunctionDef):
            raise ValueError(
                "Return annotation snippet did not parse as a function return annotation"
            )
        fd = mod.body[0]
        if fd.returns is None or not isinstance(fd.returns, cst.Annotation):
            raise ValueError("Parsed function has no Annotation for returns")
        return fd.returns
    wrapped = f"def __ann_param__(x{text}):\n    pass\n"
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as e:
        raise ValueError(f"Invalid parameter annotation syntax: {e}") from e
    if not mod.body or not isinstance(mod.body[0], cst.FunctionDef):
        raise ValueError(
            "Parameter annotation snippet did not parse as a function parameter"
        )
    fd = mod.body[0]
    if not fd.params.params:
        raise ValueError(
            "Parameter annotation snippet did not parse as a function parameter"
        )
    param0 = fd.params.params[0]
    if param0.annotation is None or not isinstance(param0.annotation, cst.Annotation):
        raise ValueError("Parsed parameter has no Annotation")
    return param0.annotation


def _normalize_snippet_indentation(code: str) -> str:
    lines = code.splitlines()
    if not lines:
        return code
    min_indent = None
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            indent = len(line) - len(stripped)
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent is None or min_indent == 0:
        return code
    normalized_lines: List[str] = []
    for line in lines:
        if line.strip():
            if len(line) >= min_indent:
                normalized_lines.append(line[min_indent:])
            else:
                normalized_lines.append(line)
        else:
            normalized_lines.append("")
    return "\n".join(normalized_lines)


def _indent_non_empty_lines(code: str, prefix: str) -> str:
    lines: List[str] = []
    for line in code.splitlines():
        if line.strip():
            lines.append(f"{prefix}{line}")
        else:
            lines.append("")
    return "\n".join(lines)


def _align_code_for_node_move_snippet(code: str, source_container: str) -> str:
    """
    Normalize ``code_for_node`` text before move parsing.

    ``code_for_node`` often places the ``def``/``class`` header at column 0 while
    body lines keep absolute indentation from the original file. That hybrid breaks
    ``_normalize_snippet_indentation`` and class-stub wrapping (docstring interiors
    get double-indented). Subtract one nesting level from over-indented body lines.
    """
    lines = code.splitlines()
    if not lines:
        return code
    header_indent: Optional[int] = None
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("def ", "async def ", "class ")):
            header_indent = len(line) - len(stripped)
            break
    if header_indent is None:
        return code
    body_indent = header_indent + 4
    if source_container not in ("class", "function") or header_indent != 0:
        return code
    dedent = 4
    fixed: List[str] = []
    for line in lines:
        if not line.strip():
            fixed.append(line)
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent >= body_indent + 4:
            fixed.append(line[dedent:])
        else:
            fixed.append(line)
    return "\n".join(fixed)


def _parse_function_def_module_level(code: str) -> cst.FunctionDef:
    normalized = _normalize_snippet_indentation(code)
    try:
        mod = cst.parse_module(normalized)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Failed to parse function snippet: {exc}") from exc
    found = _first_stmt_of_type(
        cast(List[cst.BaseStatement], list(mod.body)), cst.FunctionDef
    )
    if found is None or not isinstance(found, cst.FunctionDef):
        raise ValueError("Function snippet must contain a def statement")
    return found


def insert_target_container_kind(tree: "CSTTree", parent_node_id: str) -> str:
    """
    Container kind for insert/move target: module, class, or function body.

    Walks parents from ``parent_node_id`` (ClassDef / FunctionDef / Module).
    """
    meta = tree.metadata_map.get(parent_node_id)
    if meta is None:
        return "module"
    if meta.type == "Module":
        return "module"
    if meta.type == "ClassDef":
        return "class"
    if meta.type == "FunctionDef":
        return "function"
    parent_id = getattr(meta, "parent_id", None)
    while parent_id:
        parent_meta = tree.metadata_map.get(parent_id)
        if not parent_meta:
            break
        parent_type = getattr(parent_meta, "type", "") or ""
        if parent_type == "Module":
            return "module"
        if parent_type == "ClassDef":
            return "class"
        if parent_type == "FunctionDef":
            return "function"
        parent_id = getattr(parent_meta, "parent_id", None)
    return "module"


def class_body_indent_prefix(tree: "CSTTree", parent_node_id: str) -> str:
    """Leading whitespace for one statement nesting level inside class bodies."""
    depth = 0
    current: Optional[str] = parent_node_id
    while current:
        meta = tree.metadata_map.get(current)
        if not meta:
            break
        if meta.type == "ClassDef":
            depth += 1
        current = getattr(meta, "parent_id", None)
    if depth <= 0:
        return ""
    return "    " * depth


def def_snippet_container_kind(tree: "CSTTree", metadata: Any) -> str:
    """
    Where a FunctionDef/ClassDef replacement will be spliced: module, class, or function.

    Walks metadata parents past IndentedBlock so method-in-class resolves to ``class``.
    """
    parent_id = getattr(metadata, "parent_id", None) if metadata else None
    while parent_id:
        parent_meta = tree.metadata_map.get(parent_id)
        if not parent_meta:
            break
        parent_type = getattr(parent_meta, "type", "") or ""
        if parent_type == "Module":
            return "module"
        if parent_type == "ClassDef":
            return "class"
        if parent_type == "FunctionDef":
            return "function"
        parent_id = getattr(parent_meta, "parent_id", None)
    return "module"


def _first_stmt_of_type(
    body: List[cst.BaseStatement], node_type: type
) -> Optional[cst.CSTNode]:
    for stmt in body:
        if isinstance(stmt, node_type):
            return stmt
    return None


def _parse_function_def_in_class_stub_with_indent(
    code: str, class_body_indent: str
) -> cst.FunctionDef:
    normalized = _normalize_snippet_indentation(code)
    prefix = class_body_indent or "    "
    wrapped = (
        f"class {_SNIPPET_CLASS_NAME}:\n"
        f"{_indent_non_empty_lines(normalized, prefix)}\n"
    )
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as exc:
        raise ValueError(
            f"Failed to parse function snippet for class body: {exc}"
        ) from exc
    cls = mod.body[0] if mod.body else None
    if not isinstance(cls, cst.ClassDef):
        raise ValueError(
            "Function snippet for class body did not parse as a class stub"
        )
    found = _first_stmt_of_type(
        cast(List[cst.BaseStatement], list(cls.body.body)), cst.FunctionDef
    )
    if found is None or not isinstance(found, cst.FunctionDef):
        raise ValueError("Function snippet must contain a def statement")
    return found


def _parse_function_def_in_class_stub(code: str) -> cst.FunctionDef:
    return _parse_function_def_in_class_stub_with_indent(code, "    ")


def _parse_function_def_in_function_stub(code: str) -> cst.FunctionDef:
    normalized = _normalize_snippet_indentation(code)
    wrapped = (
        f"def {_SNIPPET_FUNC_NAME}():\n"
        f"{_indent_non_empty_lines(normalized, '    ')}\n"
    )
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as exc:
        raise ValueError(
            f"Failed to parse function snippet for nested function: {exc}"
        ) from exc
    outer = mod.body[0] if mod.body else None
    if not isinstance(outer, cst.FunctionDef):
        raise ValueError(
            "Function snippet for nested function did not parse as a function stub"
        )
    if not isinstance(outer.body, cst.IndentedBlock):
        raise ValueError("Function snippet stub has no body")
    found = _first_stmt_of_type(
        cast(List[cst.BaseStatement], list(outer.body.body)), cst.FunctionDef
    )
    if found is None or not isinstance(found, cst.FunctionDef):
        raise ValueError("Nested function snippet must contain a def statement")
    return found


def _parse_class_def_in_class_stub(code: str) -> cst.ClassDef:
    normalized = _normalize_snippet_indentation(code)
    wrapped = (
        f"class {_SNIPPET_CLASS_NAME}:\n"
        f"{_indent_non_empty_lines(normalized, '    ')}\n"
    )
    try:
        mod = cst.parse_module(wrapped)
    except cst.ParserSyntaxError as exc:
        raise ValueError(
            f"Failed to parse class snippet for nested class: {exc}"
        ) from exc
    outer = mod.body[0] if mod.body else None
    if not isinstance(outer, cst.ClassDef):
        raise ValueError("Class snippet for nested class did not parse as a class stub")
    found = _first_stmt_of_type(
        cast(List[cst.BaseStatement], list(outer.body.body)), cst.ClassDef
    )
    if found is None or not isinstance(found, cst.ClassDef):
        raise ValueError("Nested class snippet must contain a class statement")
    return found


def _snippet_is_function_def(code: str) -> bool:
    """True when the first non-empty line starts with ``def`` or ``async def``."""
    for line in code.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.startswith("def ") or stripped.startswith("async def ")
    return False


def parse_code_snippet_for_insert(
    tree: "CSTTree",
    parent_node_id: str,
    code: Optional[str] = None,
    code_lines: Optional[List[str]] = None,
) -> List[Union[cst.BaseStatement, cst.EmptyLine]]:
    """
    Parse insert snippet with parent-container awareness.

    FunctionDef snippets inserted into a class body are parsed inside a class
    stub so docstring literal interiors keep method-body indentation.
    """
    raw = _snippet_as_string(code, code_lines)
    if not raw.strip():
        return []
    container_kind = insert_target_container_kind(tree, parent_node_id)
    if container_kind == "class" and _snippet_is_function_def(raw):
        indent = class_body_indent_prefix(tree, parent_node_id)
        return [_parse_function_def_in_class_stub_with_indent(raw, indent or "    ")]
    return cast(
        List[Union[cst.BaseStatement, cst.EmptyLine]],
        list(parse_code_snippet_or_comment(code=code, code_lines=code_lines)),
    )


def parse_code_snippet_for_move(
    code: str,
    *,
    node_type: str,
    target_container: str,
    source_container: str = "module",
    class_body_indent: str = "    ",
) -> List[cst.BaseStatement]:
    """
    Parse moved source for insertion with target-container indentation.

    For ``FunctionDef`` targets inside a class: parse in a class stub with
    ``class_body_indent`` so docstring literals keep correct interior spacing.
    Module-level sources are already 0-base in ``code_for_node`` and must not
    pass through ``_align_code_for_node_move_snippet``. Class/function sources
    are aligned first, then parsed in the same stub.
    """
    if node_type == "FunctionDef":
        if target_container == "class":
            stub_code = code
            if source_container in ("class", "function"):
                stub_code = _align_code_for_node_move_snippet(code, source_container)
            return [
                _parse_function_def_in_class_stub_with_indent(
                    stub_code, class_body_indent or "    "
                )
            ]
        if target_container == "function":
            stub_code = code
            if source_container in ("class", "function"):
                stub_code = _align_code_for_node_move_snippet(code, source_container)
            return [_parse_function_def_in_function_stub(stub_code)]
        if source_container in ("class", "function"):
            code = _align_code_for_node_move_snippet(code, source_container)
        return list(parse_code_snippet(code=code))
    if node_type == "ClassDef":
        if target_container == "class":
            return [_parse_class_def_in_class_stub(code)]
        return list(parse_code_snippet(code=code))
    return cast(
        List[cst.BaseStatement],
        list(parse_code_snippet_or_comment(code=code)),
    )


def parse_code_snippet_for_def_replace(
    code: str,
    *,
    tree: "CSTTree",
    target_metadata: Any,
) -> List[cst.BaseStatement]:
    """
    Parse replacement text for FunctionDef/ClassDef with parent-aware indentation.

    Snippets use method-level indentation (4 spaces for body). When the target lives
    inside a class or function, parse inside a stub so docstring literals and body
    statements get the extra indent LibCST expects on splice.
    """
    node_type = (getattr(target_metadata, "type", "") or "") if target_metadata else ""
    container = def_snippet_container_kind(tree, target_metadata)
    if node_type == "FunctionDef" and container == "class":
        return [_parse_function_def_in_class_stub(code)]
    if node_type == "FunctionDef" and container == "function":
        return [_parse_function_def_in_function_stub(code)]
    if node_type == "ClassDef" and container == "class":
        return [_parse_class_def_in_class_stub(code)]
    return list(parse_code_snippet(code=code))


def parse_code_snippet(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> list[cst.BaseStatement]:
    """
    Parse code snippet into list of statements.

    Supports both single statements and multi-line blocks.
    Handles indentation by normalizing it before parsing.

    Args:
        code: Code snippet to parse as single string (may have indentation).
        code_lines: Code snippet as list of lines (alternative to code).
                    Prevents JSON escaping issues with multi-line code.

    Returns:
        List of CST statements.

    Raises:
        ValueError: If code cannot be parsed or both code and code_lines are provided.

    Note:
        If code_lines is provided, it takes precedence over code.
        This allows passing multi-line code without JSON escaping issues.
    """
    # Prefer code_lines over code to avoid JSON escaping issues
    if code_lines is not None:
        if code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        code = join_code_lines(code_lines)
    elif code is None:
        return []

    if not code.strip():
        return []

    normalized = _normalize_snippet_indentation(code)

    # Try parsing as module first
    try:
        mod = cst.parse_module(normalized)
        return list(mod.body)
    except cst.ParserSyntaxError:
        # If parsing as module fails, try wrapping in a function body
        # This handles cases where code is a statement sequence (not valid module-level)
        indented_lines = []
        for line in normalized.splitlines():
            if line.strip():
                indented_lines.append("    " + line)
            else:
                indented_lines.append("")
        func_body = "\n".join(indented_lines)
        func_wrapper = f"def _temp():\n{func_body}"

        try:
            mod = cst.parse_module(func_wrapper)
            if mod.body and isinstance(mod.body[0], cst.FunctionDef):
                func = mod.body[0]
                if isinstance(func.body, cst.IndentedBlock):
                    return list(func.body.body)
        except Exception:
            pass

        # Last resort: try as single statement
        try:
            stmt = cst.parse_statement(normalized)
            return [stmt]
        except Exception as e:
            raise ValueError(
                f"Failed to parse code snippet as statements: {e}. "
                "Code must be valid Python statements."
            ) from e


def parse_code_snippet_or_comment(
    code: Optional[str] = None, code_lines: Optional[List[str]] = None
) -> List[Union[cst.BaseStatement, cst.EmptyLine]]:
    """
    Parse code as statements, or as comment-only line(s) for insert.

    When the snippet is only comment(s) (e.g. "# mypy: ignore-errors"),
    parse_module returns empty body. This helper then builds EmptyLine+Comment
    node(s) so that insert can add comment lines to the module.

    Returns:
        List of statements or EmptyLine nodes (valid for Module.body).
    """
    statements = parse_code_snippet(code=code, code_lines=code_lines)
    if statements:
        return cast(List[Union[cst.BaseStatement, cst.EmptyLine]], statements)
    raw = (join_code_lines(code_lines) if code_lines is not None else code) or ""
    stripped = raw.strip()
    if not stripped or not stripped.startswith("#"):
        return []
    # Comment-only: build EmptyLine(s) with Comment
    result: List[Union[cst.BaseStatement, cst.EmptyLine]] = []
    for line in stripped.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("#"):
            result.append(cst.EmptyLine(comment=cst.Comment(value=line_stripped)))
    return result
