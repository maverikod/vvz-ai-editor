"""Deterministic format-selection resolver (concept C-011).

Scope: this module answers exactly one question -- "which single format
plugin applies to this open request?" -- and nothing else. It defines no
registry and no concrete plugins; the plugin registry (``register_format_plugin``,
``get_format_plugin``, ``list_format_plugins``) and every concrete plugin
(python, bsl, json, yaml, toml, plain_text, ...) are delivered by sibling
and later steps and must not be imported or stubbed here per {p062}. This
module instead accepts the available plugin set and the registry lookup as
injected parameters -- a plain mapping or iterable of plugin-like objects,
and any object exposing a single ``get_format_plugin(format_id)`` method.

Selection rules ({p061}, {p062}, {p063}, {p095}), applied literally:

* An explicit ``format_id`` has unconditional priority. Resolution happens
  solely through ``registry.get_format_plugin`` on that branch; the file
  path/extension is never read, parsed, or otherwise inspected, no matter
  whether it is present, absent, unknown, or would itself conflict.
* Without ``format_id``, resolution goes only through the pre-built,
  uniqueness-validated ``file_extensions`` table (see
  :func:`build_extension_table`). A missing or unknown extension is an
  unconditional error -- never a fallback and never a trigger for content
  analysis.
* Content sniffing, ``detect`` calls, and plugin probing (trying candidate
  plugins to see which one accepts the content) are forbidden everywhere in
  this module. Plain-text fallback is a separate, later stage triggered
  only after a resolved plugin's own ``parse_document`` reports a content
  parse failure; selection itself never triggers or signals it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, Union, runtime_checkable

from tree_engine.errors import ErrorCode

__all__ = [
    "FormatPluginLookup",
    "FormatSelectionError",
    "build_extension_table",
    "resolve_format_plugin",
]


@runtime_checkable
class FormatPluginLookup(Protocol):
    """Minimal registry surface this resolver depends on.

    Mirrors the future registry's ``get_format_plugin(format_id)`` entry
    point without importing the (not yet delivered) registry module: any
    object exposing this one method -- a real registry, a test double, or a
    thin adapter -- can be injected as ``registry`` below.
    """

    def get_format_plugin(self, format_id: str) -> Any:
        ...


class FormatSelectionError(Exception):
    """Raised for a deterministic format-selection failure.

    Always carries one of the catalog codes defined in
    :mod:`tree_engine.errors` -- :attr:`ErrorCode.FORMAT_UNKNOWN_EXTENSION`
    or :attr:`ErrorCode.FORMAT_EXTENSION_CONFLICT` for the two failure
    modes this module produces. No other exception type is raised by
    :func:`resolve_format_plugin` or :func:`build_extension_table` for a
    selection failure; a lookup failure from an injected ``registry`` is
    the registry's own concern and propagates unchanged.
    """

    def __init__(self, *, error_code: ErrorCode, message: str = "", **details: Any) -> None:
        self.error_code: ErrorCode = error_code
        self.details: Mapping[str, Any] = dict(details)
        super().__init__(message or f"{error_code.value}: {self.details}")


# A plugin-like item accepted by `build_extension_table`: either a
# FormatPluginMetadata instance directly, or any object exposing a
# `.metadata` attribute/property that returns one (e.g. a
# FormatPluginContract implementation). Left untyped (`Any`) deliberately:
# this module must not import the contract module's concrete types to stay
# decoupled from exactly which shape the caller injects.
PluginLike = Any


def _metadata_of(plugin: PluginLike) -> Any:
    """Return the plugin's static metadata, without reading any content.

    If ``plugin`` exposes a ``.metadata`` attribute or property, that value
    is used (this covers a ``FormatPluginContract`` implementation, whose
    ``metadata`` property returns a ``FormatPluginMetadata``). Otherwise
    ``plugin`` is assumed to already be metadata-shaped (it must expose
    ``format_id`` and ``file_extensions``).
    """

    return getattr(plugin, "metadata", plugin)


def _normalize_extension(extension: str) -> str:
    """Normalize an extension string for table storage and lookup.

    Strips one leading dot (if present) and lower-cases the remainder.
    Purely syntactic string handling -- no filesystem access, no content
    inspection.
    """

    normalized = extension.strip()
    if normalized.startswith("."):
        normalized = normalized[1:]
    return normalized.lower()


def _extension_from_path(file_path: str) -> str:
    """Extract and normalize the extension from a file path string.

    Uses ``os.path.splitext`` on the path string only: this never opens,
    reads, or otherwise touches the file itself. Returns ``""`` when the
    path has no extension.
    """

    _, raw_extension = os.path.splitext(file_path)
    return _normalize_extension(raw_extension) if raw_extension else ""


def build_extension_table(
    plugins: Union[Mapping[str, PluginLike], Iterable[PluginLike]],
) -> Mapping[str, str]:
    """Build the extension -> format_id table from registered plugin metadata.

    ``plugins`` is the injected, available plugin set: either a mapping
    (``format_id`` -> plugin-like object) or a plain iterable of
    plugin-like objects. This function never imports a registry module or
    a concrete plugin module; it only reads the static ``format_id`` and
    ``file_extensions`` fields off whatever metadata each item exposes (see
    :func:`_metadata_of`). No file content, ``detect`` call, or plugin
    probing is involved.

    Uniqueness is validated here, at build time, per {p062}: two different
    plugins (different ``format_id``) claiming the same normalized
    extension is a configuration error, raised immediately as
    :class:`FormatSelectionError` carrying
    :attr:`ErrorCode.FORMAT_EXTENSION_CONFLICT`. The same plugin listing
    the same extension more than once (e.g. via an alias entry) is not a
    conflict.

    The returned table covers whatever the injected plugin set declares;
    when the caller injects the baseline first-version plugin set, the
    result covers the baseline mapping (txt -> plain_text, py/pyi ->
    python, bsl -> bsl, json -> json, yaml/yml -> yaml, toml -> toml).
    """

    candidates: Iterable[PluginLike] = (
        plugins.values() if isinstance(plugins, Mapping) else plugins
    )

    table: Dict[str, str] = {}
    for plugin in candidates:
        metadata = _metadata_of(plugin)
        format_id = metadata.format_id
        for raw_extension in metadata.file_extensions:
            extension = _normalize_extension(raw_extension)
            if not extension:
                continue
            existing_format_id = table.get(extension)
            if existing_format_id is not None and existing_format_id != format_id:
                raise FormatSelectionError(
                    error_code=ErrorCode.FORMAT_EXTENSION_CONFLICT,
                    message=(
                        f"extension '.{extension}' is claimed by both "
                        f"'{existing_format_id}' and '{format_id}'"
                    ),
                    extension=extension,
                    format_ids=(existing_format_id, format_id),
                )
            table[extension] = format_id

    return dict(table)


def resolve_format_plugin(
    *,
    format_id: Optional[str] = None,
    file_path: Optional[str] = None,
    registry: FormatPluginLookup,
    extension_table: Mapping[str, str],
) -> Any:
    """Deterministically resolve exactly one format plugin.

    Explicit-id priority ({p061}, {p095}): when ``format_id`` is given, it
    has unconditional priority. Resolution happens solely through
    ``registry.get_format_plugin(format_id)`` -- ``file_path`` is not read,
    not parsed for an extension, and not inspected in any way on this
    branch, even when it is absent, has an unknown extension, or would
    itself conflict.

    Extension fallback table ({p062}, {p063}): without ``format_id``,
    resolution goes only through ``extension_table``, the pre-built,
    uniqueness-validated mapping produced by :func:`build_extension_table`.
    A missing ``file_path``, a path with no extension, or an extension not
    present in ``extension_table`` all raise :class:`FormatSelectionError`
    carrying :attr:`ErrorCode.FORMAT_UNKNOWN_EXTENSION` -- there is no
    fallback and no partial match.

    Neither branch performs content sniffing, calls a ``detect`` method, or
    probes candidate plugins by trial; this function never triggers or
    signals a plain-text fallback -- that is a separate, later stage
    reacting to a resolved plugin's own parse failure, not a concern of
    selection.
    """

    if format_id is not None:
        return registry.get_format_plugin(format_id)

    extension = _extension_from_path(file_path) if file_path else ""
    if not extension or extension not in extension_table:
        raise FormatSelectionError(
            error_code=ErrorCode.FORMAT_UNKNOWN_EXTENSION,
            message=(
                "no unambiguous format plugin is registered for "
                + (f"path {file_path!r}" if file_path else "a missing file extension")
            ),
            file_path=file_path,
            extension=extension or None,
        )

    resolved_format_id = extension_table[extension]
    return registry.get_format_plugin(resolved_format_id)
