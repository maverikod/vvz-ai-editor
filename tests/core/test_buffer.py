"""
Tests for tree_engine.core.buffer (concept C-005, IncrementalSourceBuffer),
scoped to SourceBuffer's correctness: byte-for-byte round-trip, per-edit
listener notifications, and rejection of invalid edit ranges. Piece-count /
cost scaling under many edits is covered by a sibling step and is out of
scope here.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Tuple

import pytest

from tree_engine.core.buffer import BufferEditListener, EditNotification, SourceBuffer

SOURCE = (
    b"# header comment\n"
    b"first line of content\n"
    b"\n"
    b"middle section here\n"
    b"    indented text\n"
    b"\n"
    b"final line\n"
)


class RecordingListener:
    """Spy BufferEditListener recording every notification it receives."""

    def __init__(self) -> None:
        self.calls: List[EditNotification] = []

    def on_buffer_edit(self, notification: EditNotification) -> None:
        self.calls.append(notification)


class ReferenceModel:
    """Independent bytearray model mirroring the expected edit semantics.

    Used to compute expected buffer contents after a sequence of edits
    without relying on the piece-table implementation under test.
    """

    def __init__(self, source: bytes) -> None:
        self.data = bytearray(source)

    def apply(self, start: int, end: int, replacement: bytes) -> None:
        self.data[start:end] = replacement

    @property
    def contents(self) -> bytes:
        return bytes(self.data)


# --------------------------------------------------------------------------
# 1. byte-for-byte round trip
# --------------------------------------------------------------------------


class TestByteForByteRoundTrip:
    def test_fresh_buffer_serializes_to_original_source(self) -> None:
        buf = SourceBuffer(SOURCE)
        assert buf.serialize() == SOURCE

    def test_empty_source_round_trips(self) -> None:
        buf = SourceBuffer(b"")
        assert buf.serialize() == b""
        assert len(buf) == 0

    def test_single_edit_leaves_surrounding_bytes_identical(self) -> None:
        start = SOURCE.index(b"first")
        end = start + len(b"first")
        replacement = b"1ST!!"
        model = ReferenceModel(SOURCE)
        model.apply(start, end, replacement)

        buf = SourceBuffer(SOURCE)
        buf.apply_edit(start, end, replacement, ("body", "0"))

        result = buf.serialize()
        assert result == model.contents
        # Prefix and suffix around the edit are untouched, byte-for-byte.
        assert result[:start] == SOURCE[:start]
        assert result[start + len(replacement) :] == SOURCE[end:]

    def test_pure_insertion_round_trips(self) -> None:
        model = ReferenceModel(SOURCE)
        model.apply(0, 0, b">>> ")
        buf = SourceBuffer(SOURCE)
        buf.apply_edit(0, 0, b">>> ", ("body", "0"))
        assert buf.serialize() == model.contents
        assert buf.serialize().endswith(SOURCE)

    def test_pure_deletion_round_trips(self) -> None:
        start, end = 0, len(b"# header comment\n")
        model = ReferenceModel(SOURCE)
        model.apply(start, end, b"")
        buf = SourceBuffer(SOURCE)
        buf.apply_edit(start, end, b"", ("body", "0"))
        assert buf.serialize() == model.contents
        assert buf.serialize() == SOURCE[end:]

    def test_multiple_non_overlapping_edits_preserve_untouched_regions(self) -> None:
        # Applied right-to-left so each edit's coordinates stay valid
        # against the still-unshifted left portion of the buffer, in both
        # the buffer under test and the independent reference model.
        words = [b"indented", b"middle", b"first"]  # rightmost occurrence first
        edits: List[Tuple[int, int, bytes]] = []
        for word in words:
            start = SOURCE.index(word)
            end = start + len(word)
            edits.append((start, end, word.upper()))
        edits.sort(key=lambda item: item[0], reverse=True)

        model = ReferenceModel(SOURCE)
        buf = SourceBuffer(SOURCE)
        for start, end, replacement in edits:
            model.apply(start, end, replacement)
            buf.apply_edit(start, end, replacement, ("body",))

        assert buf.serialize() == model.contents
        # Regions between and around the three edits are untouched.
        first_start = SOURCE.index(b"first")
        assert buf.serialize().startswith(SOURCE[:first_start])
        assert b"\n\n" in buf.serialize()  # blank lines survive verbatim
        assert b"final line\n" in buf.serialize()

    def test_sequence_of_edits_matches_independent_model(self) -> None:
        model = ReferenceModel(SOURCE)
        buf = SourceBuffer(SOURCE)
        # Deterministic sequence, each computed against the *current*
        # buffer length so both buf and model stay in lockstep.
        plan = [
            (0, 0, b"// "),
            (len(model.contents), len(model.contents), b"\n# appended\n"),
            (5, 11, b"HEADER"),
        ]
        for start, end, replacement in plan:
            model.apply(start, end, replacement)
            buf.apply_edit(start, end, replacement, ("root",))
            assert buf.serialize() == model.contents

    def test_iter_regions_flags_untouched_as_original_and_replacement_as_added(
        self,
    ) -> None:
        start = SOURCE.index(b"first")
        end = start + len(b"first")
        replacement = b"1ST!!"
        buf = SourceBuffer(SOURCE)
        buf.apply_edit(start, end, replacement, ("body",))

        regions = list(buf.iter_regions())
        assert [chunk for _is_original, chunk in regions] == [
            SOURCE[:start],
            replacement,
            SOURCE[end:],
        ]
        assert [is_original for is_original, _chunk in regions] == [True, False, True]

    def test_iter_regions_on_fresh_buffer_is_entirely_original(self) -> None:
        buf = SourceBuffer(SOURCE)
        regions = list(buf.iter_regions())
        assert all(is_original for is_original, _chunk in regions)
        assert b"".join(chunk for _is_original, chunk in regions) == SOURCE


# --------------------------------------------------------------------------
# 2. edit notification payload
# --------------------------------------------------------------------------


class TestEditNotificationPayload:
    def test_single_edit_notification_has_correct_payload(self) -> None:
        buf = SourceBuffer(SOURCE)
        listener = RecordingListener()
        buf.add_listener(listener)

        start = SOURCE.index(b"first")
        end = start + len(b"first")
        node_path = ("module", "statements", "2")
        notification = buf.apply_edit(start, end, b"1ST!!", node_path)

        assert len(listener.calls) == 1
        delivered = listener.calls[0]
        assert delivered == notification
        assert delivered.byte_range == (start, end)
        assert delivered.replacement == b"1ST!!"
        assert delivered.node_path == node_path

    def test_node_path_is_coerced_to_tuple(self) -> None:
        buf = SourceBuffer(SOURCE)
        listener = RecordingListener()
        buf.add_listener(listener)
        buf.apply_edit(0, 0, b"x", ["a", "b"])
        assert listener.calls[0].node_path == ("a", "b")

    def test_multiple_listeners_each_notified_once_in_registration_order(self) -> None:
        buf = SourceBuffer(SOURCE)
        order: List[str] = []

        class TrackingListener:
            def __init__(self, name: str) -> None:
                self.name = name

            def on_buffer_edit(self, notification: EditNotification) -> None:
                order.append(self.name)

        first = TrackingListener("first")
        second = TrackingListener("second")
        buf.add_listener(first)
        buf.add_listener(second)

        buf.apply_edit(0, 0, b"x", ("root",))

        assert order == ["first", "second"]

    def test_batch_of_edits_produces_one_ordered_notification_each(self) -> None:
        buf = SourceBuffer(SOURCE)
        listener = RecordingListener()
        buf.add_listener(listener)

        # Right-to-left so each edit's range is expressed in coordinates
        # unaffected by the edits still to come.
        raw = [
            (b"indented", b"REINDENTED", ("d",)),
            (b"middle", b"MID", ("c",)),
            (b"first", b"FIRST", ("b",)),
        ]
        planned: List[Tuple[int, int, bytes, Tuple[str, ...]]] = []
        for word, replacement, path in raw:
            start = SOURCE.index(word)
            planned.append((start, start + len(word), replacement, path))
        planned.sort(key=lambda item: item[0], reverse=True)

        for start, end, replacement, path in planned:
            buf.apply_edit(start, end, replacement, path)

        assert len(listener.calls) == len(planned)
        for delivered, (start, end, replacement, path) in zip(listener.calls, planned):
            assert delivered.byte_range == (start, end)
            assert delivered.replacement == replacement
            assert delivered.node_path == path

    def test_remove_listener_stops_future_notifications(self) -> None:
        buf = SourceBuffer(SOURCE)
        listener = RecordingListener()
        buf.add_listener(listener)
        buf.apply_edit(0, 0, b"x", ("a",))
        buf.remove_listener(listener)
        buf.apply_edit(0, 0, b"y", ("b",))
        assert len(listener.calls) == 1

    def test_remove_unknown_listener_is_a_no_op(self) -> None:
        buf = SourceBuffer(SOURCE)
        never_added = RecordingListener()
        buf.remove_listener(never_added)  # must not raise
        buf.apply_edit(0, 0, b"x", ("a",))
        assert never_added.calls == []


# --------------------------------------------------------------------------
# 3. invalid ranges are rejected without corrupting the buffer
# --------------------------------------------------------------------------


class TestInvalidEditsRejected:
    def test_start_greater_than_end_raises_value_error(self) -> None:
        buf = SourceBuffer(SOURCE)
        with pytest.raises(ValueError):
            buf.apply_edit(5, 2, b"x", ("a",))

    def test_negative_start_raises_value_error(self) -> None:
        buf = SourceBuffer(SOURCE)
        with pytest.raises(ValueError):
            buf.apply_edit(-1, 2, b"x", ("a",))

    def test_end_beyond_buffer_length_raises_value_error(self) -> None:
        buf = SourceBuffer(SOURCE)
        with pytest.raises(ValueError):
            buf.apply_edit(0, len(SOURCE) + 1, b"x", ("a",))

    def test_edit_on_empty_buffer_out_of_range_raises_value_error(self) -> None:
        buf = SourceBuffer(b"")
        with pytest.raises(ValueError):
            buf.apply_edit(0, 1, b"x", ("a",))

    def test_invalid_edit_does_not_notify_listeners(self) -> None:
        buf = SourceBuffer(SOURCE)
        listener = RecordingListener()
        buf.add_listener(listener)
        with pytest.raises(ValueError):
            buf.apply_edit(5, 2, b"x", ("a",))
        assert listener.calls == []

    def test_invalid_edit_does_not_corrupt_buffer_state(self) -> None:
        buf = SourceBuffer(SOURCE)
        with pytest.raises(ValueError):
            buf.apply_edit(-1, 2, b"x", ("a",))
        assert buf.serialize() == SOURCE
        assert len(buf) == len(SOURCE)

    def test_buffer_accepts_valid_edits_after_a_rejected_one(self) -> None:
        buf = SourceBuffer(SOURCE)
        with pytest.raises(ValueError):
            buf.apply_edit(100, 2, b"x", ("a",))
        buf.apply_edit(0, 1, b"#", ("a",))
        assert buf.serialize() == b"#" + SOURCE[1:]
