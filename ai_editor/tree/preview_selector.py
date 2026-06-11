"""
PreviewSelector and per-format render thresholds (C-017).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from ai_editor.tree.contracts import NodeId, validate_short_id

DEFAULT_FULL_TEXT_MAX_LINES: int = 200
FORMAT_EXTENSION_MAP: Dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "json": (".json",),
    "yaml": (".yaml", ".yml"),
    "markdown": (".md",),
    "text": (".txt", ".rst"),
}
DEFAULT_THRESHOLDS: Dict[str, int] = {k: 200 for k in FORMAT_EXTENSION_MAP}


class PreviewRenderMode(str, Enum):
    INLINE = "inline"
    DRILLDOWN = "drilldown"


class PreviewSelectorError(ValueError):
    """Malformed slice, unknown form, or unknown short_id in list."""


@dataclass(frozen=True)
class PreviewSelectorConfig:
    full_text_max_lines: Mapping[str, int] = field(
        default_factory=lambda: dict(DEFAULT_THRESHOLDS)
    )
    max_chars: Optional[int] = None


@dataclass(frozen=True)
class PreviewSelector:
    _kind: str  # "slice" | "ids" | "all"
    _slice_start: Optional[int] = None
    _slice_end: Optional[int] = None
    _short_ids: Optional[tuple[NodeId, ...]] = None

    @classmethod
    def parse(cls, raw: Union[str, Sequence[int], None]) -> PreviewSelector:
        if raw is None or raw == "" or raw == []:
            return cls(_kind="all")

        if isinstance(raw, str):
            if ":" in raw:
                return cls._parse_slice(raw)
            raise PreviewSelectorError("unsupported selector form")

        if isinstance(raw, Sequence):
            if len(raw) == 0:
                return cls(_kind="all")
            try:
                ids = tuple(validate_short_id(int(v)) for v in raw)
            except (TypeError, ValueError) as exc:
                raise PreviewSelectorError(str(exc)) from exc
            return cls(_kind="ids", _short_ids=ids)

        raise PreviewSelectorError("unsupported selector form")

    @classmethod
    def _parse_slice(cls, raw: str) -> PreviewSelector:
        if raw.count(":") != 1:
            raise PreviewSelectorError("malformed slice")
        start_part, end_part = raw.split(":", 1)
        start: Optional[int]
        end: Optional[int]
        try:
            start = None if start_part == "" else int(start_part)
            end = None if end_part == "" else int(end_part)
        except ValueError as exc:
            raise PreviewSelectorError("malformed slice") from exc
        return cls(_kind="slice", _slice_start=start, _slice_end=end)

    def apply(self, blocks: Sequence[Any]) -> List[Any]:
        block_list = list(blocks)
        if self._kind == "all":
            return block_list
        if self._kind == "slice":
            start = 0 if self._slice_start is None else self._slice_start
            end = len(block_list) if self._slice_end is None else self._slice_end
            return block_list[start:end]
        if self._kind == "ids":
            assert self._short_ids is not None
            by_id = {block.short_id: block for block in block_list}
            result: List[Any] = []
            for sid in self._short_ids:
                block = by_id.get(sid)
                if block is None:
                    raise PreviewSelectorError(f"unknown short_id: {sid!r}")
                result.append(block)
            return result
        raise PreviewSelectorError("unsupported selector form")

    @staticmethod
    def decide_render_mode(
        *,
        format_key: str,
        line_span: int,
        config: PreviewSelectorConfig,
    ) -> PreviewRenderMode:
        threshold = config.full_text_max_lines.get(
            format_key, DEFAULT_FULL_TEXT_MAX_LINES
        )
        if threshold == 0:
            return PreviewRenderMode.DRILLDOWN
        if line_span < threshold:
            return PreviewRenderMode.INLINE
        return PreviewRenderMode.DRILLDOWN


def format_key_from_extension(ext: str) -> str:
    normalized = ext.lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    for format_key, extensions in FORMAT_EXTENSION_MAP.items():
        if normalized in extensions:
            return format_key
    raise PreviewSelectorError(f"unknown extension: {ext!r}")


def paginate_envelope(serialized: str, max_chars: Optional[int]) -> str:
    if max_chars is None or max_chars <= 0:
        return serialized
    if len(serialized) <= max_chars:
        return serialized
    return serialized[:max_chars] + "\u2026"
