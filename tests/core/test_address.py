"""Unit tests for tree_engine.core.address.

Scoped to normalize_node_address ({j9rh}), the to_str/from_str external
string-form helpers ({p080}), and build_node_address_view ({p021}).
Deliberately excludes short_id allocation lifecycle and replace_node_id
atomicity, owned by sibling test modules.

The document stand-in wires the real ``tree_engine.core.short_id``
``ShortIdMap`` (``allocate``/``get_node_id``/``get_short_id``/``release``)
behind the ``document.resolve_short_id`` duck-typed accessor that
``normalize_node_address`` consults, so these tests exercise address.py and
short_id.py working together rather than a hand-written fake resolver.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import pytest

from tree_engine.core.address import (
    AmbiguousAddressError,
    ForeignDocumentAddressError,
    NodeAddressView,
    UnknownAddressError,
    build_node_address_view,
    from_str,
    normalize_node_address,
    to_str,
)
from tree_engine.core.identity import NodeAddress
from tree_engine.core.short_id import ShortIdMap, ShortIdMapSnapshot


class _Document:
    """Minimal in-memory document exposing exactly what address.py reads.

    ``nodes_by_id`` and ``resolve_short_id`` are the duck-typed surface
    documented in address.py's module docstring. ``short_ids`` is the real
    ``ShortIdMap``, consulted by ``resolve_short_id`` -- never bypassed.
    ``document_version`` is extra bookkeeping used only to assert no
    partial execution on error paths; address.py never reads or writes it.
    """

    def __init__(self, document_id: Optional[UUID] = None) -> None:
        self.document_id = document_id if document_id is not None else uuid.uuid4()
        self.nodes_by_id: Dict[UUID, object] = {}
        self.short_ids = ShortIdMap()
        self.document_version = 0

    def add_node(self) -> UUID:
        node_id = uuid.uuid4()
        self.nodes_by_id[node_id] = object()
        self.short_ids.allocate(node_id)
        return node_id

    def resolve_short_id(self, short_id: int) -> List[UUID]:
        node_id = self.short_ids.get_node_id(short_id)
        return [node_id] if node_id is not None else []


def _snapshot_state(document: _Document) -> Tuple[int, ShortIdMapSnapshot]:
    """Capture everything a failed normalize_node_address call must not touch."""

    return (document.document_version, document.short_ids.snapshot())


@pytest.fixture
def document() -> _Document:
    """A document with a gap: short_id 2 is allocated then freed."""

    doc = _Document()
    doc.node_a = doc.add_node()  # short_id 1
    node_freed = doc.add_node()  # short_id 2
    doc.node_b = doc.add_node()  # short_id 3
    doc.freed_short_id = doc.short_ids.get_short_id(node_freed)
    doc.short_ids.release(node_freed)
    return doc


@pytest.fixture
def foreign_document() -> _Document:
    """A second, independent document to exercise the foreign-address case."""

    doc = _Document()
    doc.node_a = doc.add_node()  # short_id 1
    doc.add_node()  # short_id 2
    doc.add_node()  # short_id 3
    doc.high_short_id_node = doc.add_node()  # short_id 4, out of `document`'s range
    return doc


# normalize_node_address: accepted forms


class TestNormalizeNodeAddressAcceptance:
    def test_uuid_node_id_resolves_to_itself(self, document: _Document) -> None:
        resolved = normalize_node_address(
            document, document.node_a, current_document_id=document.document_id
        )
        assert resolved == document.node_a

    def test_int_short_id_resolves_via_bidirectional_map(self, document: _Document) -> None:
        short_id = document.short_ids.get_short_id(document.node_b)
        resolved = normalize_node_address(
            document, short_id, current_document_id=document.document_id
        )
        assert resolved == document.node_b

    def test_hex_short_id_matches_equivalent_int_form(self, document: _Document) -> None:
        short_id = document.short_ids.get_short_id(document.node_a)
        hex_form = f"0x{short_id:x}"
        resolved_hex = normalize_node_address(
            document, hex_form, current_document_id=document.document_id
        )
        resolved_int = normalize_node_address(
            document, short_id, current_document_id=document.document_id
        )

        assert resolved_hex == resolved_int == document.node_a

    def test_decimal_string_short_id_matches_equivalent_int_form(
        self, document: _Document
    ) -> None:
        """A short_id spelled in decimal as a ``str`` is the same address as the
        ``int`` it spells. Regression: a plain ``"3"`` matched no branch -- not
        the ``0x`` prefix, not ``document_id:node_id``, not a bare UUID -- and
        fell through to ``UnknownAddressError``, so every caller carrying a
        short_id through a string-typed protocol field was rejected outright."""
        short_id = document.short_ids.get_short_id(document.node_b)
        resolved_decimal = normalize_node_address(
            document, str(short_id), current_document_id=document.document_id
        )
        resolved_int = normalize_node_address(
            document, short_id, current_document_id=document.document_id
        )

        assert resolved_decimal == resolved_int == document.node_b

    def test_every_live_short_id_resolves_alike_in_all_three_spellings(
        self, document: _Document
    ) -> None:
        """int, decimal string and hex string are one address form, per node."""
        for node_id in (document.node_a, document.node_b):
            short_id = document.short_ids.get_short_id(node_id)
            resolved = {
                normalize_node_address(
                    document, form, current_document_id=document.document_id
                )
                for form in (short_id, str(short_id), f"0x{short_id:x}")
            }
            assert resolved == {node_id}


# normalize_node_address: error paths, and no-partial-execution on each


class TestNormalizeNodeAddressErrors:
    def test_freed_short_id_decimal_string_form_raises(self, document: _Document) -> None:
        """The decimal spelling is not a way around the map: a released short_id
        is unresolvable in every spelling, and the rejection touches nothing."""
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(
                document, str(document.freed_short_id),
                current_document_id=document.document_id,
            )

        assert _snapshot_state(document) == before

    def test_decimal_zero_and_non_ascii_digits_are_not_short_ids(
        self, document: _Document
    ) -> None:
        """``"0"`` is not a positive short_id, and a non-ASCII digit is not a
        decimal spelling at all -- neither may be reinterpreted as one."""
        for bad in ("0", "00", "٣"):  # the last is ARABIC-INDIC DIGIT THREE
            before = _snapshot_state(document)
            with pytest.raises(UnknownAddressError):
                normalize_node_address(
                    document, bad, current_document_id=document.document_id
                )
            assert _snapshot_state(document) == before

    def test_unknown_uuid_raises(self, document: _Document) -> None:
        unknown_id = uuid.uuid4()
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError) as exc_info:
            normalize_node_address(document, unknown_id, current_document_id=document.document_id)

        assert exc_info.value.raw_address == unknown_id
        assert _snapshot_state(document) == before

    def test_never_allocated_short_id_raises(self, document: _Document) -> None:
        never_allocated = document.short_ids.snapshot().next_short_id + 100
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(
                document, never_allocated, current_document_id=document.document_id
            )

        assert _snapshot_state(document) == before

    def test_freed_short_id_int_form_raises(self, document: _Document) -> None:
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(
                document, document.freed_short_id, current_document_id=document.document_id
            )

        assert _snapshot_state(document) == before

    def test_freed_short_id_hex_form_raises(self, document: _Document) -> None:
        hex_form = f"0x{document.freed_short_id:x}"
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(document, hex_form, current_document_id=document.document_id)

        assert _snapshot_state(document) == before

    def test_ambiguous_short_id_raises(self, document: _Document) -> None:
        def ambiguous_resolver(short_id: int) -> List[UUID]:
            return [uuid.uuid4(), uuid.uuid4()]

        short_id = document.short_ids.get_short_id(document.node_a)
        before = _snapshot_state(document)
        with pytest.raises(AmbiguousAddressError):
            normalize_node_address(
                document,
                short_id,
                current_document_id=document.document_id,
                resolve_short_id=ambiguous_resolver,
            )

        assert _snapshot_state(document) == before

    def test_foreign_node_address_instance_raises(
        self, document: _Document, foreign_document: _Document
    ) -> None:
        foreign_address = NodeAddress(
            document_id=foreign_document.document_id, node_id=foreign_document.node_a
        )
        before = _snapshot_state(document)
        with pytest.raises(ForeignDocumentAddressError) as exc_info:
            normalize_node_address(
                document, foreign_address, current_document_id=document.document_id
            )
        assert exc_info.value.document_id == foreign_document.document_id
        assert _snapshot_state(document) == before

    def test_foreign_serialized_string_form_raises(
        self, document: _Document, foreign_document: _Document
    ) -> None:
        text = to_str(
            NodeAddress(document_id=foreign_document.document_id, node_id=foreign_document.node_a)
        )
        before = _snapshot_state(document)
        with pytest.raises(ForeignDocumentAddressError):
            normalize_node_address(document, text, current_document_id=document.document_id)

        assert _snapshot_state(document) == before

    def test_uuid_valid_in_foreign_document_is_never_silently_resolved(
        self, document: _Document, foreign_document: _Document
    ) -> None:
        # Valid in `foreign_document`, absent from `document`: must reject,
        # never silently resolve against the wrong document.
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(
                document, foreign_document.node_a, current_document_id=document.document_id
            )

        assert foreign_document.node_a not in document.nodes_by_id
        assert _snapshot_state(document) == before

    def test_short_id_out_of_range_for_foreign_document_is_never_silently_resolved(
        self, document: _Document, foreign_document: _Document
    ) -> None:
        # One short_id higher than `document` ever allocated: meaningful in
        # `foreign_document`, must never resolve here.
        foreign_short_id = foreign_document.short_ids.get_short_id(
            foreign_document.high_short_id_node
        )
        before = _snapshot_state(document)
        with pytest.raises(UnknownAddressError):
            normalize_node_address(
                document, foreign_short_id, current_document_id=document.document_id
            )

        assert _snapshot_state(document) == before


# NodeAddress external string-form serialization ({p080})


class TestNodeAddressSerialization:
    def test_intra_document_address_round_trips_with_implicit_document_id(
        self, document: _Document
    ) -> None:
        address = NodeAddress(node_id=document.node_a)
        assert address.document_id is None

        resolved = normalize_node_address(
            document, address, current_document_id=document.document_id
        )
        assert resolved == document.node_a

    def test_cross_document_address_serializes_with_explicit_document_id(
        self, foreign_document: _Document
    ) -> None:
        address = NodeAddress(
            document_id=foreign_document.document_id, node_id=foreign_document.node_a
        )

        text = to_str(address)
        assert text == f"{foreign_document.document_id}:{foreign_document.node_a}"

        round_tripped = from_str(text)
        assert round_tripped == address
        assert round_tripped.document_id == foreign_document.document_id
        assert round_tripped.node_id == foreign_document.node_a

    def test_implicit_form_cannot_serialize_without_explicit_document_id(self) -> None:
        address = NodeAddress(node_id=uuid.uuid4())
        with pytest.raises(ValueError):
            to_str(address)


# short_id_hex + node_id view contract ({p021})


class TestNodeViewShortIdHexContract:
    def test_view_pairs_short_id_hex_with_node_id(self, document: _Document) -> None:
        short_id = document.short_ids.get_short_id(document.node_b)
        view = build_node_address_view(document.node_b, short_id)

        assert isinstance(view, NodeAddressView)
        assert view.node_id == str(document.node_b)
        assert view.short_id_hex == f"0x{short_id:x}"

    def test_view_pair_identifies_same_node_through_normalize(
        self, document: _Document
    ) -> None:
        short_id = document.short_ids.get_short_id(document.node_a)
        view = build_node_address_view(document.node_a, short_id)

        resolved_via_uuid = normalize_node_address(
            document, uuid.UUID(view.node_id), current_document_id=document.document_id
        )
        resolved_via_hex = normalize_node_address(
            document, view.short_id_hex, current_document_id=document.document_id
        )

        assert resolved_via_uuid == resolved_via_hex == document.node_a
