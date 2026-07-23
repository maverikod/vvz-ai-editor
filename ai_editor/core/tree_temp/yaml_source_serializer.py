"""
TreeNode to round-trip YAML SourceSerializer with comment restoration (C-006, C-004).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from io import StringIO
from typing import Any, List, Optional, Tuple, Union, cast

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import CommentMark
from ruamel.yaml.tokens import CommentToken

from ai_editor.core.tree_temp.tree_node import (
    TreeNode,
    TreeNodeType,
    validate_node_constraints,
)

_ERR = "Invalid tree for YAML serialization:"


def _validate_subtree(node: TreeNode, member_of_object: bool) -> None:
    validate_node_constraints(node)
    if member_of_object:
        if node.key is None or node.key == "":
            raise ValueError(f"{_ERR} object member must have non-empty key")
    else:
        if node.key is not None:
            raise ValueError(f"{_ERR} unexpected key on non-member node")
    if node.type in ("object", "array"):
        children = node.children if node.children is not None else []
        next_member = node.type == "object"
        for ch in children:
            _validate_subtree(ch, next_member)


def _ruamel_body(stored: str) -> str:
    """Strip a leading ``#`` from each stored comment line.

    Ruamel's own comment-emission helpers re-add the hash prefix.
    """
    lines: List[str] = []
    for ln in stored.splitlines():
        t = ln.strip()
        if t.startswith("#"):
            t = t[1:].lstrip()
        lines.append(t)
    return "\n".join(lines)


def _finalize_dump_text(s: str) -> str:
    """Remove trailing ``...`` document-end marker from ruamel scalar dumps."""
    lines = s.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if lines and lines[-1].strip() == "...":
        lines.pop()
    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"
    return out


def _scalar_pyval(node: TreeNode) -> Any:
    t: TreeNodeType = node.type
    if t == "string":
        return cast(str, node.value)
    if t == "number":
        v = node.value
        if isinstance(v, bool):
            raise ValueError(f"{_ERR} number value must be int or float")
        return v
    if t == "boolean":
        return bool(node.value)
    if t == "null":
        return None
    raise ValueError(f"{_ERR} expected scalar node")


def _tree_to_commented(node: TreeNode) -> Any:
    if node.type == "object":
        cm: CommentedMap = CommentedMap()
        for ch in node.children or []:
            if ch.key is None:
                raise ValueError(f"{_ERR} object member must have non-empty key")
            cm[ch.key] = _tree_to_commented(ch)
        if node.flow_style is not None:
            if node.flow_style:
                cm.fa.set_flow_style()
            else:
                cm.fa.set_block_style()
        return cm
    if node.type == "array":
        seq: CommentedSeq = CommentedSeq()
        for ch in node.children or []:
            seq.append(_tree_to_commented(ch))
        if node.flow_style is not None:
            if node.flow_style:
                seq.fa.set_flow_style()
            else:
                seq.fa.set_block_style()
        return seq
    return _scalar_pyval(node)


def _eol_comment_arg(text: str) -> str:
    s = text.strip()
    if not s:
        return text
    return text if s.startswith("#") else text


def _emit_container_end_inline(c: Union[CommentedMap, CommentedSeq], text: str) -> None:
    arg = _eol_comment_arg(text)
    if not arg.endswith("\n"):
        arg = arg + "\n"
    c.yaml_end_comment_extend([CommentToken(arg, CommentMark(0))])


def _apply_comments(
    node: TreeNode,
    c: Any,
    *,
    seq_item: Optional[Tuple[CommentedSeq, int]] = None,
) -> None:
    if node.type in ("object", "array"):
        if seq_item is not None:
            seq, idx = seq_item
            if node.comment_before:
                seq.yaml_set_comment_before_after_key(
                    idx, before=_ruamel_body(node.comment_before)
                )
            if node.comment_inline:
                seq.yaml_add_eol_comment(_eol_comment_arg(node.comment_inline), key=idx)
        else:
            if node.comment_before:
                cast(Union[CommentedMap, CommentedSeq], c).yaml_set_start_comment(
                    _ruamel_body(node.comment_before)
                )
            if node.comment_inline:
                _emit_container_end_inline(
                    cast(Union[CommentedMap, CommentedSeq], c), node.comment_inline
                )
    elif seq_item is not None:
        seq, idx = seq_item
        if node.comment_before:
            seq.yaml_set_comment_before_after_key(
                idx, before=_ruamel_body(node.comment_before)
            )
        if node.comment_inline:
            seq.yaml_add_eol_comment(_eol_comment_arg(node.comment_inline), key=idx)

    if node.type == "object":
        cm = cast(CommentedMap, c)
        for ch in node.children or []:
            assert ch.key is not None
            sub = cm[ch.key]
            if ch.comment_before:
                cm.yaml_set_comment_before_after_key(
                    ch.key, before=_ruamel_body(ch.comment_before)
                )
            if ch.comment_inline:
                cm.yaml_add_eol_comment(_eol_comment_arg(ch.comment_inline), key=ch.key)
            _apply_comments(ch, sub)
    elif node.type == "array":
        seqn = cast(CommentedSeq, c)
        for i, ch in enumerate(node.children or []):
            sub = seqn[i]
            if ch.comment_before:
                seqn.yaml_set_comment_before_after_key(
                    i, before=_ruamel_body(ch.comment_before)
                )
            if ch.comment_inline:
                seqn.yaml_add_eol_comment(_eol_comment_arg(ch.comment_inline), key=i)
            _apply_comments(ch, sub)


def _emit_scalar_root(yaml: YAML, node: TreeNode) -> str:
    buf = StringIO()
    yaml.dump(_scalar_pyval(node), buf)
    body = _finalize_dump_text(buf.getvalue()).rstrip("\n")
    out_lines: List[str] = []
    if node.comment_before:
        for ln in node.comment_before.splitlines():
            raw = ln.strip()
            out_lines.append(
                ln if raw.startswith("#") else ("# " + raw if raw else "#")
            )
    out_lines.append(body)
    if node.comment_inline:
        out_lines[-1] = out_lines[-1] + " " + node.comment_inline.strip()
    joined = "\n".join(out_lines)
    if not joined.endswith("\n"):
        joined += "\n"
    return joined


def serialize_yaml_source(root_nodes: List[TreeNode]) -> str:
    """Serialize root TreeNode list to UTF-8 YAML text with comments (C-006).

    Root shape (aligned with source_spec and T-002 parser):
    - Zero roots: emit YAML flow empty sequence exactly `[]` followed by
      newline (parses as empty root array).
    - One root, type object: YAML mapping as document root.
    - One root, scalar: that scalar as document root (plain YAML scalar).
    - More than one root: YAML block or flow sequence at document root
      listing each TreeNode subtree in order (same "expanded root array"
      convention as JSON parser when the source was a sequence at top level).
    - Single root with type array: invalid — raise ValueError like JSON serializer.

    Use YAML(typ='rt'); preserve_quotes=True; default_flow_style=False;
    write to StringIO; return .getvalue() with trailing newline.

    Raises:
        ValueError: prefix "Invalid tree for YAML serialization:" for
            field/type inconsistencies (same object/array/scalar key/value
            invariants as T-003 serializer text).
    """
    if any(n.type == "array" for n in root_nodes):
        raise ValueError(f"{_ERR} unexpected root array wrapper")
    for r in root_nodes:
        if not isinstance(r.stable_id, str) or not r.stable_id.strip():
            raise ValueError(f"{_ERR} stable_id required on every node")
        _validate_subtree(r, False)

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.default_flow_style = False

    if len(root_nodes) == 0:
        return "[]\n"
    if len(root_nodes) == 1:
        n0 = root_nodes[0]
        if n0.type not in ("object", "array"):
            return _emit_scalar_root(yaml, n0)
        root = _tree_to_commented(n0)
        _apply_comments(n0, root)
        buf = StringIO()
        yaml.dump(root, buf)
        out = buf.getvalue()
        if not out.endswith("\n"):
            out += "\n"
        return out
    seq_root = CommentedSeq()
    for n in root_nodes:
        seq_root.append(_tree_to_commented(n))
    for i, n in enumerate(root_nodes):
        _apply_comments(n, seq_root[i], seq_item=(seq_root, i))
    buf = StringIO()
    yaml.dump(seq_root, buf)
    out = buf.getvalue()
    if not out.endswith("\n"):
        out += "\n"
    return out
