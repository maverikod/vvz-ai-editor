"""Contract tests for tree_engine.core.reparse.reparse_edited_node (concept
C-006, {p098}/{p099}).

Covers, each as a distinct test: the capability/node-kind gate that must be
consulted before ``parse_fragment`` is ever invoked; the string-result
outcome, which must leave the edited node textual and childless; the
structured-result outcome, which must keep the edited node's own UUID4 as
the container while every new child is preflighted and applied atomically
through the shared validation/operations pipeline; and every {p099}
rejection/rollback path (parser exception, wrong return type, empty
result, and a common-model contract violation), each asserting the exact
:class:`~tree_engine.errors.ErrorCode` and that nothing -- including no
plain-text fallback -- was ever written. A further test counts calls to
confirm a batch of K edited nodes produces exactly K fragment-level
parses and never a whole-document one.

Deliberately excludes ``set_body``/source-fragment update behavior and
attribute/identifier updates -- those belong to the sibling
``test_node_content_updates.py`` file. Uses minimal duck-typed node/
document stand-ins, matching the structural contract already documented
on ``validate_mutation``/``insert`` and relied on by ``reparse.py`` itself.
"""

from __future__ import annotations

import inspect
import itertools
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

import pytest

from tree_engine.core.reparse import (
    STATUS_SKIPPED,
    STATUS_STRUCTURED,
    STATUS_TEXTUAL,
    ReparseError,
    reparse_edited_node,
)
from tree_engine.errors import ErrorCode


# ---------------------------------------------------------------------------
# Minimal duck-typed node/document stand-ins (mirrors test_validation.py's,
# extended with ``kind`` so the same class also satisfies reparse.py's own
# common-model node shape check).
# ---------------------------------------------------------------------------


class _Node:
    def __init__(
        self,
        node_id: Any,
        *,
        short_id: Any = None,
        kind: str = "node",
        children: Optional[Sequence["_Node"]] = None,
        parent: Optional["_Node"] = None,
    ) -> None:
        self.node_id = node_id
        self.short_id = short_id
        self.kind = kind
        self.children: List["_Node"] = list(children) if children else []
        self.parent = parent


class _Document:
    def __init__(self, nodes: Sequence[_Node]) -> None:
        self.document_id = uuid.uuid4()
        self.nodes_by_id: Dict[Any, _Node] = {}
        self.short_id_index: Dict[Any, Any] = {}
        for node in nodes:
            self.nodes_by_id[node.node_id] = node
            if node.short_id is not None:
                self.short_id_index[node.short_id] = node.node_id


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_edited_node(*, kind: str = "container") -> tuple:
    node = _Node(_new_id(), kind=kind)
    return node, _Document([node])


def _short_id_allocator(start: int = 1) -> Callable[[], int]:
    counter = itertools.count(start)
    return lambda: next(counter)


def _counting(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``fn`` recording every call as (args, kwargs) on ``.calls``."""

    calls: List[Any] = []

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        return fn(*args, **kwargs)

    _wrapped.calls = calls  # type: ignore[attr-defined]
    return _wrapped


# ---------------------------------------------------------------------------
# Gating: the capability/node-kind decision is consulted before parsing.
# ---------------------------------------------------------------------------


def test_reparse_gating_by_capability_and_node_kind() -> None:
    edited_node, document = _make_edited_node(kind="scalar_leaf")

    def _never_called(text: str, *, source_format_id: str) -> str:
        raise AssertionError("parse_fragment must not be called")

    parse_fragment = _counting(_never_called)

    outcome = reparse_edited_node(
        document, edited_node, "new leaf text",
        source_format_id="python",
        admits_nested_structure=lambda node: False,
        parse_fragment=parse_fragment,
    )

    assert outcome.status == STATUS_SKIPPED
    assert outcome.node_id == edited_node.node_id
    assert parse_fragment.calls == []
    assert edited_node.children == []
    assert document.nodes_by_id == {edited_node.node_id: edited_node}


def test_reparse_batch_produces_one_fragment_parse_per_node_and_no_whole_document_parse() -> None:
    # No whole-document parse capability is even injectable: reparse.py's
    # only parser hook is the fragment-level one.
    parameters = inspect.signature(reparse_edited_node).parameters
    assert "parse_fragment" in parameters
    assert not any("document" in name for name in parameters if "parse" in name)

    parse_fragment = _counting(lambda text, *, source_format_id: text.upper())

    k = 3
    for _ in range(k):
        edited_node, document = _make_edited_node(kind="scalar_leaf")
        outcome = reparse_edited_node(
            document, edited_node, "x",
            source_format_id="python",
            admits_nested_structure=lambda node: True,
            parse_fragment=parse_fragment,
        )
        assert outcome.status == STATUS_TEXTUAL

    # Exactly K fragment-level calls for K independently reparsed elements
    # of a batch -- never one call for the whole batch, never a call per
    # element plus a trailing whole-document one.
    assert len(parse_fragment.calls) == k


# ---------------------------------------------------------------------------
# String result: node stays textual, no child routing.
# ---------------------------------------------------------------------------


def test_reparse_string_result_leaves_node_textual() -> None:
    edited_node, document = _make_edited_node(kind="markup_block")
    original_children = list(edited_node.children)

    outcome = reparse_edited_node(
        document, edited_node, "plain text, no recognized structure",
        source_format_id="markdown",
        admits_nested_structure=lambda node: True,
        parse_fragment=lambda text, *, source_format_id: text,
    )

    assert outcome.status == STATUS_TEXTUAL
    assert outcome.text == "plain text, no recognized structure"
    assert outcome.node_id == edited_node.node_id
    assert outcome.applied == ()
    assert edited_node.children == original_children == []
    assert document.nodes_by_id == {edited_node.node_id: edited_node}


# ---------------------------------------------------------------------------
# Structured result: container identity preserved, children preflighted
# and applied atomically through validation.py/operations.py.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("as_list", [False, True])
def test_reparse_structured_result_atomic_child_application(as_list: bool) -> None:
    edited_node, document = _make_edited_node(kind="container")
    original_node_id = edited_node.node_id

    child_a = _Node(None, kind="child_a")
    child_b = _Node(None, kind="child_b")
    new_roots = [child_a, child_b] if as_list else [child_a]
    raw_result = list(new_roots) if as_list else child_a

    id_calls: List[uuid.UUID] = []

    def _generate_id() -> uuid.UUID:
        fresh = uuid.uuid4()
        id_calls.append(fresh)
        return fresh

    outcome = reparse_edited_node(
        document, edited_node, "<a/><b/>" if as_list else "<a/>",
        source_format_id="xml",
        admits_nested_structure=lambda node: True,
        parse_fragment=lambda text, *, source_format_id: raw_result,
        generate_node_id=_generate_id,
        next_short_id=_short_id_allocator(start=500),
    )

    assert outcome.status == STATUS_STRUCTURED
    # UUID4 continuity: the edited node keeps its own identity as container.
    assert outcome.node_id == original_node_id
    assert edited_node.node_id == original_node_id
    assert isinstance(edited_node.node_id, uuid.UUID) and edited_node.node_id.version == 4

    assert len(outcome.applied) == len(new_roots)
    assert edited_node.children == new_roots
    for child in new_roots:
        assert child.parent is edited_node
        # Fresh UUID4 assigned to every new child.
        assert isinstance(child.node_id, uuid.UUID) and child.node_id.version == 4
        assert child.node_id in id_calls
        # Fresh short_id assigned via the shared allocator, atomically.
        assert child.short_id is not None
        assert document.nodes_by_id[child.node_id] is child
        assert document.short_id_index[child.short_id] == child.node_id

    assert len({child.node_id for child in new_roots}) == len(new_roots)
    assert len(id_calls) == len(new_roots)
    expected_ids = {edited_node.node_id} | {child.node_id for child in new_roots}
    assert set(document.nodes_by_id) == expected_ids


# ---------------------------------------------------------------------------
# Rejection/rollback: every {p099} failure mode raises a classified
# ReparseError and leaves the node and the index exactly as they were --
# never a plain-text fallback.
# ---------------------------------------------------------------------------


def _raising_parser(text: str, *, source_format_id: str) -> Any:
    raise RuntimeError("parser blew up")


def _wrong_type_parser(text: str, *, source_format_id: str) -> Any:
    return 12345  # not a str, not a recognizable node shape


def _empty_result_parser(text: str, *, source_format_id: str) -> Any:
    return []  # claims to be a node set, holds nothing


def _malformed_node_parser(text: str, *, source_format_id: str) -> Any:
    return [_Node(_new_id(), kind="")]  # kind is required to be a non-empty str


def _duplicate_node_id_parser(text: str, *, source_format_id: str) -> Any:
    shared_id = _new_id()
    return [_Node(shared_id, kind="dup_a"), _Node(shared_id, kind="dup_b")]


def _incompatible_child_parser(text: str, *, source_format_id: str) -> Any:
    return [_Node(None, kind="rejected_child")]


_REJECTION_CASES = [
    ("parser_raises", _raising_parser, ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED, None),
    ("wrong_return_type", _wrong_type_parser, ErrorCode.FORMAT_FRAGMENT_PARSE_FAILED, None),
    ("empty_result", _empty_result_parser, ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR, None),
    ("malformed_common_model_node", _malformed_node_parser, ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR, None),
    ("duplicate_node_id_in_batch", _duplicate_node_id_parser, ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR, None),
    (
        "fails_preflight_against_new_parent",
        _incompatible_child_parser,
        ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
        lambda parent, position, incoming: False,
    ),
]


@pytest.mark.parametrize(
    "case_id, parser, expected_code, is_type_compatible",
    _REJECTION_CASES,
    ids=[case[0] for case in _REJECTION_CASES],
)
def test_reparse_rejection_and_rollback_error_codes(
    case_id: str,
    parser: Callable[..., Any],
    expected_code: ErrorCode,
    is_type_compatible: Optional[Callable[[Any, Optional[str], Any], bool]],
) -> None:
    edited_node, document = _make_edited_node(kind="container")
    original_node_id = edited_node.node_id

    with pytest.raises(ReparseError) as exc_info:
        reparse_edited_node(
            document, edited_node, "some new text",
            source_format_id="python",
            admits_nested_structure=lambda node: True,
            parse_fragment=parser,
            is_type_compatible=is_type_compatible,
            next_short_id=_short_id_allocator(),
        )

    assert exc_info.value.code == expected_code
    # Rollback: the node and the index are exactly as they were -- and
    # since a ReparseError was raised rather than any ReparseOutcome
    # returned, no plain-text fallback (or any other outcome) ever
    # occurred in its place.
    assert edited_node.node_id == original_node_id
    assert edited_node.children == []
    assert edited_node.parent is None
    assert document.nodes_by_id == {edited_node.node_id: edited_node}
    assert document.short_id_index == {}
