"""
Round-trip YAML SourceParser: text to TreeNode forest with comment fields (C-005, C-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from io import StringIO
from typing import Any, Dict, List, Optional, Union, cast

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ai_editor.core.tree_temp.tree_node import TreeNode, TreeNodeType


def _token_text(tok: Any) -> str:
    return str(getattr(tok, "value", tok))


def _join_comment_tokens(tokens: Optional[List[Any]]) -> Optional[str]:
    if not tokens:
        return None
    parts: List[str] = []
    for tok in tokens:
        if tok is None:
            continue
        parts.append(_token_text(tok).rstrip("\n"))
    if not parts:
        return None
    return "\n".join(parts)


def _doc_pre_comment(data: Any) -> Optional[str]:
    ca = getattr(data, "ca", None)
    if not ca or not ca.comment or len(ca.comment) < 2:
        return None
    pre = ca.comment[1]
    return _join_comment_tokens(pre if isinstance(pre, list) else None)


def _split_inline_and_spill(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Split ruamel EOL / item slot text into inline for this node and spill for the next."""
    t = raw.rstrip("\n")
    if not t:
        return None, None
    if t.startswith("\n"):
        body = t[1:].lstrip("\n")
        return (None, body if body else None)
    lines = t.split("\n")
    first = lines[0]
    if len(lines) == 1:
        return first, None
    rest = "\n".join(lines[1:])
    return first, rest if rest else None


def _merge_before(*parts: Optional[str]) -> Optional[str]:
    out: List[str] = []
    for p in parts:
        if p:
            out.append(p)
    if not out:
        return None
    return "\n".join(out)


def _yaml_key_str(key: Any) -> str:
    if isinstance(key, str):
        return key
    return str(key)


def _new_stable_id() -> str:
    """Create parser-owned identity; YAML payload fields never supply IDs."""
    return str(uuid.uuid4())


def _tree_type_for_value(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "boolean"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, (CommentedMap, dict)) and not isinstance(val, CommentedSeq):
        return "object"
    if isinstance(val, (CommentedSeq, list)):
        return "array"
    return "object"


def _build_scalar(val: Any) -> TreeNode:
    t = _tree_type_for_value(val)
    if t == "object" or t == "array":
        raise ValueError("Internal: expected scalar")
    pyval: Any
    if t == "null":
        pyval = None
    elif t == "boolean":
        pyval = bool(val)
    elif t == "number":
        pyval = val
    else:
        # Keep the original str value as-is (rather than coercing via str()):
        # ruamel yields ScalarString subclasses (SingleQuotedScalarString,
        # DoubleQuotedScalarString, ...) for typ='rt' loads with
        # preserve_quotes=True. Preserving the subclass here (TreeNode.value
        # is Any and str subclasses still satisfy the "string" type contract)
        # lets the serializer round-trip the original quote style for
        # unmutated subtrees without any TreeNode schema change.
        pyval = val
    nt: TreeNodeType = cast(
        TreeNodeType,
        t,
    )
    return TreeNode(stable_id=_new_stable_id(), type=nt, value=pyval, children=None)


def _build_object(data: Union[CommentedMap, Dict[Any, Any]]) -> TreeNode:
    children: List[TreeNode] = []
    doc_top = _doc_pre_comment(data)
    obj = TreeNode(
        stable_id=_new_stable_id(),
        type="object",
        value=None,
        children=children,
        comment_before=doc_top,
    )
    pending: Optional[str] = None
    for key in data:
        kstr = _yaml_key_str(key)
        parts: List[Optional[str]] = []
        if pending:
            parts.append(pending)
            pending = None
        cell: Optional[List[Any]] = None
        if isinstance(data, CommentedMap) and data.ca:
            cell = data.ca.items.get(key)
        if cell:
            parts.append(_join_comment_tokens(cell[1] if len(cell) > 1 else None))
            parts.append(_join_comment_tokens(cell[3] if len(cell) > 3 else None))
        inl: Optional[str] = None
        if cell and len(cell) > 2 and cell[2] is not None:
            inl, spill = _split_inline_and_spill(_token_text(cell[2]))
            if spill:
                pending = _merge_before(pending, spill)
        else:
            inl = None
        child = _build_value(data[key])
        child.key = kstr
        cb = _merge_before(*parts)
        if cb:
            child.comment_before = cb
        if inl:
            child.comment_inline = inl
        children.append(child)
    if pending:
        # NOTE (45b27a37 audit): a comment still pending after the last key
        # is really a footer/trailing comment of this mapping, not a
        # "before" comment of the last key -- attaching it to
        # last.comment_before (as done here) moves it from after the last
        # value to before the last key on round-trip. A correct fix needs a
        # dedicated container "footer comment" slot: TreeNode.comment_inline
        # already has an established, relied-upon meaning for a *nested*
        # container (EOL comment on the enclosing key/list-item line, applied
        # by the parent's _apply_comments before recursing) and ruamel's
        # yaml_end_comment_extend/ca.end is not consumed by this ruamel
        # version's emitter, so neither can safely carry a footer comment
        # without a TreeNode schema change. Deferred; see 45b27a37 report.
        if children:
            last = children[-1]
            last.comment_before = _merge_before(last.comment_before, pending)
    return obj


def _build_array_container(data: Union[CommentedSeq, List[Any]]) -> TreeNode:
    ch: List[TreeNode] = []
    doc_top = _doc_pre_comment(data)
    arr = TreeNode(
        stable_id=_new_stable_id(),
        type="array",
        value=None,
        children=ch,
        comment_before=doc_top,
    )
    pending: Optional[str] = None
    for i in range(len(data)):
        parts: List[Optional[str]] = []
        if pending:
            parts.append(pending)
            pending = None
        cell: Optional[List[Any]] = None
        if isinstance(data, CommentedSeq) and data.ca:
            cell = data.ca.items.get(i)
        inl: Optional[str] = None
        if cell and cell[0] is not None:
            inl, spill = _split_inline_and_spill(_token_text(cell[0]))
            if spill:
                pending = _merge_before(pending, spill)
        if cell and len(cell) > 1:
            parts.append(_join_comment_tokens(cell[1]))
        cb = _merge_before(*parts)
        child = _build_value(data[i])
        if cb:
            child.comment_before = cb
        if inl:
            child.comment_inline = inl
        ch.append(child)
    if pending and ch:
        # See the NOTE in _build_object: this mis-attaches a trailing/footer
        # comment as the last element's comment_before. Deferred for the same
        # reason (no schema slot for a container footer comment that would
        # not collide with comment_inline's existing nested-container
        # meaning).
        last = ch[-1]
        last.comment_before = _merge_before(last.comment_before, pending)
    return arr


def _build_value(data: Any) -> TreeNode:
    if isinstance(data, CommentedSeq) or (
        isinstance(data, list) and not isinstance(data, CommentedMap)
    ):
        return _build_array_container(cast(Union[CommentedSeq, List[Any]], data))
    if isinstance(data, (CommentedMap, dict)):
        return _build_object(cast(Union[CommentedMap, Dict[Any, Any]], data))
    return _build_scalar(data)


def _document_roots(data: Any) -> List[TreeNode]:
    """Dispatch top-level YAML value to root TreeNode list per T-002."""
    if isinstance(data, CommentedSeq) or (
        isinstance(data, list) and not isinstance(data, dict)
    ):
        seq = cast(Union[CommentedSeq, List[Any]], data)
        roots: List[TreeNode] = []
        pending: Optional[str] = None
        first_el = True
        for i in range(len(seq)):
            parts: List[Optional[str]] = []
            if first_el:
                doc = _doc_pre_comment(seq)
                if doc:
                    parts.append(doc)
            first_el = False
            if pending:
                parts.append(pending)
                pending = None
            cell: Optional[List[Any]] = None
            if isinstance(seq, CommentedSeq) and seq.ca:
                cell = seq.ca.items.get(i)
            inl: Optional[str] = None
            if cell and cell[0] is not None:
                inl, spill = _split_inline_and_spill(_token_text(cell[0]))
                if spill:
                    pending = _merge_before(pending, spill)
            if cell and len(cell) > 1:
                parts.append(_join_comment_tokens(cell[1]))
            cb = _merge_before(*parts)
            child = _build_value(seq[i])
            if cb:
                child.comment_before = cb
            if inl:
                child.comment_inline = inl
            roots.append(child)
        if pending and roots:
            last = roots[-1]
            last.comment_before = _merge_before(last.comment_before, pending)
        return roots
    if isinstance(data, (CommentedMap, dict)):
        return [_build_object(cast(Union[CommentedMap, Dict[Any, Any]], data))]
    node = _build_scalar(data)
    doc = _doc_pre_comment(data)
    if doc:
        node.comment_before = doc
    return [node]


def parse_yaml_source(source_text: str) -> List[TreeNode]:
    """Parse YAML (round-trip) into root-level TreeNode list (C-005).

    Raises:
        ValueError: message starts \"Invalid YAML:\" on ruamel scanner/parser errors or unsupported
        document shape when a document is empty of nodes after parse.
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    try:
        data = yaml.load(StringIO(source_text))
    except Exception as e:
        raise ValueError(f"Invalid YAML: {e}") from e
    if data is None:
        raise ValueError("Invalid YAML: empty document")
    try:
        return _document_roots(data)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid YAML: {e}") from e
