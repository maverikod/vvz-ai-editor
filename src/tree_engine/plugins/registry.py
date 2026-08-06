"""The single format-plugin registry (concept C-010, {p055}, {p059}, {p101}).

Scope: the one authority for plugin registration, lookup, and lazy
entry-point discovery, plus the public ``convert``/``generate_output`` call
surface built on top of it. Does not define the plugin contract
(``tree_engine.plugins.contract``), the CORE-side boundary
(``tree_engine.core.plugin_boundary``), deterministic extension-based
selection (``tree_engine.plugins.selection`` -- T-002), or any concrete
plugin (T-002/T-003/T-004). ``FormatPluginRegistry`` is exactly the object
``resolve_format_plugin`` expects as its ``registry`` parameter: any object
exposing ``get_format_plugin(format_id)``.

Registration ({p055}): ``register_format_plugin``/``unregister_format_plugin``/
``get_format_plugin``/``list_format_plugins`` are the only mutation/lookup
surface. A ``format_id``, alias, or file extension already claimed by a
*different* plugin is a configuration error, never silently overwritten;
re-registering the *same* ``format_id`` requires explicit ``replace=True``.

Lazy entry-point discovery ({p059}, {p101}): plugins advertise themselves
under the standard entry-point group ``ENTRY_POINT_GROUP``. The registry
reads entry-point *metadata* (name, value) via ``importlib.metadata`` --
no import needed for that -- and calls ``entry_point.load()`` only the
first time that ``format_id`` is actually requested. Nothing here scans
``sys.path``, imports every installed distribution, or runs discovery code
beyond the standard entry-point index; nothing runs at core import time --
discovery happens only inside a ``FormatPluginRegistry`` instance's own
methods, on demand.

Errors: every failure here is a catalog code from
``tree_engine.errors.ErrorCode``, wrapped in :class:`PluginRegistrationError`
(configuration errors) or :class:`FormatPluginNotFoundError` (lookup
absence) -- no bare ``KeyError``/``ValueError``, no silent ``None``.
"""

from __future__ import annotations

from importlib import metadata as importlib_metadata
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple

from tree_engine.errors import ErrorCode
from tree_engine.plugins.contract import FormatPluginContract, FormatPluginMetadata

__all__ = [
    "ENTRY_POINT_GROUP",
    "PluginRegistrationError",
    "FormatPluginNotFoundError",
    "FormatPluginRegistry",
    "convert",
    "generate_output",
]

# Standard entry-point group an installable format-plugin package
# advertises itself under ({p101}). Entry-point *value* is
# ``"module:attribute"`` -- a module-level ``FormatPluginContract``
# instance or a zero-arg callable returning one, e.g. ``PYTHON_FORMAT_PLUGIN``
# in ``tree_engine.plugins.python.plugin``.
ENTRY_POINT_GROUP = "tree_engine.format_plugins"

# Only the major component of a plugin's contract_version must match;
# an incompatible major is rejected before import, never silently accepted.
_SUPPORTED_CONTRACT_MAJOR = "1"


class PluginRegistrationError(Exception):
    """Registration- or discovery-time configuration error.

    Covers a ``format_id``/alias/extension conflict, a malformed or
    unresolvable entry point, plugin metadata that fails structural
    validation, and an incompatible ``contract_version`` -- every case
    where the registry refuses a plugin, as opposed to failing to find one
    already accepted.
    """

    def __init__(self, *, error_code: ErrorCode, message: str, **details: Any) -> None:
        self.error_code: ErrorCode = error_code
        self.details: Mapping[str, Any] = dict(details)
        super().__init__(message)


class FormatPluginNotFoundError(Exception):
    """Raised when ``get_format_plugin`` cannot resolve ``format_id``.

    Always carries :attr:`ErrorCode.FORMAT_PLUGIN_NOT_FOUND` -- the single
    explicit failure signal {p053} requires instead of ``None`` or a bare
    ``KeyError``.
    """

    error_code: ErrorCode = ErrorCode.FORMAT_PLUGIN_NOT_FOUND

    def __init__(self, *, format_id: str) -> None:
        self.format_id = format_id
        super().__init__(f"no format plugin is registered for format_id {format_id!r}")


class _EntryPointRecord:
    """A not-yet-loaded entry-point candidate, identified by its own name.

    Uniqueness of ``format_id`` (the entry point's ``name``) is checked
    without loading the plugin. The plugin object is loaded (``.load()``)
    exactly once, on the first call to :meth:`resolve`.
    """

    __slots__ = ("entry_point", "format_id", "_loaded")

    def __init__(self, entry_point: Any, format_id: str) -> None:
        self.entry_point = entry_point
        self.format_id = format_id
        self._loaded: Optional[FormatPluginContract] = None

    def resolve(self) -> FormatPluginContract:
        """Import (on first call only) and validate the plugin, then cache it."""

        if self._loaded is not None:
            return self._loaded
        try:
            candidate = self.entry_point.load()
        except Exception as exc:  # noqa: BLE001 - re-raised as a catalog error
            raise PluginRegistrationError(
                error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                message=f"entry point {self.entry_point.name!r} in group {ENTRY_POINT_GROUP!r} failed to load: {exc}",
                entry_point=self.entry_point.name,
            ) from exc
        plugin = candidate() if isinstance(candidate, type) else candidate
        _validate_plugin(plugin, source=f"entry point {self.entry_point.name!r}")
        if plugin.metadata.format_id != self.format_id:
            raise PluginRegistrationError(
                error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                message=(
                    f"entry point {self.entry_point.name!r} advertises format_id {self.format_id!r} "
                    f"but loaded plugin declares {plugin.metadata.format_id!r}"
                ),
                entry_point=self.entry_point.name,
            )
        self._loaded = plugin
        return plugin


def _validate_plugin(plugin: Any, *, source: str) -> None:
    """Validate a resolved plugin's metadata shape ({p055}, {p056}): a
    ``metadata`` property yielding :class:`FormatPluginMetadata` with a
    non-empty ``format_id``/``plugin_version`` and a supported
    ``contract_version`` -- never file-content probing or sniffing.
    """

    metadata = getattr(plugin, "metadata", None)
    if not isinstance(metadata, FormatPluginMetadata):
        raise PluginRegistrationError(
            error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
            message=f"{source} did not resolve to a FormatPluginContract with valid metadata",
        )
    for field_name in ("format_id", "plugin_version"):
        if not getattr(metadata, field_name):
            raise PluginRegistrationError(
                error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                message=f"{source} declares an empty {field_name}",
            )
    _check_contract_version(metadata.contract_version, source=source)


def _check_contract_version(contract_version: str, *, source: str) -> None:
    major = (contract_version or "").split(".", 1)[0]
    if major != _SUPPORTED_CONTRACT_MAJOR:
        raise PluginRegistrationError(
            error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
            message=(
                f"{source} declares contract_version {contract_version!r}, "
                f"incompatible with supported major {_SUPPORTED_CONTRACT_MAJOR!r}"
            ),
            contract_version=contract_version,
        )


class FormatPluginRegistry:
    """The single authority for format-plugin registration and lookup.

    Satisfies ``tree_engine.plugins.selection.FormatPluginLookup`` (a plain
    ``get_format_plugin(format_id)`` method), so an instance is exactly what
    ``resolve_format_plugin``/``build_extension_table`` expect to be
    injected as ``registry``/among ``plugins``.
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, FormatPluginContract] = {}
        self._alias_index: Dict[str, str] = {}
        self._extension_index: Dict[str, str] = {}
        self._entry_points: Dict[str, _EntryPointRecord] = {}
        self._entry_points_scanned = False

    # -- manual registration ({p055}) ------------------------------------

    def register_format_plugin(
        self, plugin: FormatPluginContract, *, replace: bool = False
    ) -> None:
        """Register ``plugin`` under its declared identity.

        Re-registering an already-registered ``format_id`` requires
        ``replace=True``, else :class:`PluginRegistrationError`. A
        ``format_id``, alias, or extension already claimed by a
        *different* plugin is always a configuration error, ``replace`` or
        not -- ``replace`` only lets a plugin overwrite its own prior entry.
        """

        _validate_plugin(plugin, source=f"plugin {plugin!r}")
        metadata = plugin.metadata
        format_id = metadata.format_id

        if format_id in self._plugins and not replace:
            raise PluginRegistrationError(
                error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                message=(
                    f"format_id {format_id!r} is already registered; pass "
                    "replace=True to re-register it"
                ),
                format_id=format_id,
            )

        names = list(self._claimed_names(metadata))
        for kind, name, index in names:
            owner = index.get(name)
            if owner is not None and owner != format_id:
                raise PluginRegistrationError(
                    error_code=ErrorCode.FORMAT_EXTENSION_CONFLICT
                    if kind == "extension"
                    else ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                    message=(
                        f"{kind} {name!r} is already claimed by format_id "
                        f"{owner!r}, cannot register it for {format_id!r}"
                    ),
                    **{kind: name, "existing_format_id": owner, "format_id": format_id},
                )

        self._unindex(format_id)
        self._plugins[format_id] = plugin
        for _, name, index in names:
            index[name] = format_id
        self._entry_points.pop(format_id, None)

    def unregister_format_plugin(self, format_id: str) -> None:
        """Remove ``format_id`` and every alias/extension it claimed.

        Silently accepts an unknown ``format_id``: a no-op, not an error.
        """

        self._unindex(format_id)
        self._plugins.pop(format_id, None)
        self._entry_points.pop(format_id, None)

    def get_format_plugin(self, format_id: str) -> FormatPluginContract:
        """Resolve ``format_id`` (a primary id or alias).

        Order: an already-registered/loaded plugin first, then lazy
        entry-point discovery ({p059}, {p101}) -- importing at most the one
        matching entry point. Raises :class:`FormatPluginNotFoundError`
        when nothing matches.
        """

        resolved_id = self._alias_index.get(format_id, format_id)
        plugin = self._plugins.get(resolved_id)
        if plugin is not None:
            return plugin

        self._ensure_entry_points_scanned()
        record = self._entry_points.get(format_id) or self._entry_points.get(resolved_id)
        if record is not None:
            plugin = record.resolve()
            self.register_format_plugin(plugin, replace=True)
            return plugin

        raise FormatPluginNotFoundError(format_id=format_id)

    def list_format_plugins(self) -> Tuple[FormatPluginMetadata, ...]:
        """Return metadata for every currently *loaded* plugin.

        Deliberately does not force-load every discoverable entry point --
        that would defeat laziness ({p059}). Call :meth:`get_format_plugin`
        first for a ``format_id`` to bring it into this list.
        """

        return tuple(plugin.metadata for plugin in self._plugins.values())

    # -- lazy entry-point discovery ({p059}, {p101}) ----------------------

    def _load_entry_point_plugins(self) -> None:
        """Index (but do not import) every candidate entry point, once.

        Reads ``importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)``
        -- package index metadata, not a ``sys.path`` scan and not an
        import of any distribution. Each candidate's ``format_id`` (the
        entry point's own ``name``) is checked against already-known names
        before it is indexed; nothing is imported here.
        """

        if self._entry_points_scanned:
            return
        self._entry_points_scanned = True

        try:
            candidates = importlib_metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception as exc:  # noqa: BLE001 - surfaced as a configuration error
            raise PluginRegistrationError(
                error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                message=f"failed to read entry-point group {ENTRY_POINT_GROUP!r}: {exc}",
            ) from exc

        for entry_point in candidates:
            format_id = entry_point.name
            if not format_id:
                raise PluginRegistrationError(
                    error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                    message=(
                        f"entry point {entry_point!r} in group {ENTRY_POINT_GROUP!r} "
                        "has an empty name"
                    ),
                )
            if format_id in self._plugins or format_id in self._entry_points:
                raise PluginRegistrationError(
                    error_code=ErrorCode.FORMAT_PLUGIN_CONTRACT_ERROR,
                    message=(
                        f"entry point {entry_point.name!r} in group "
                        f"{ENTRY_POINT_GROUP!r} duplicates an already-known format_id"
                    ),
                    format_id=format_id,
                )
            self._entry_points[format_id] = _EntryPointRecord(entry_point, format_id)

    def _ensure_entry_points_scanned(self) -> None:
        self._load_entry_point_plugins()

    # -- internal bookkeeping ----------------------------------------------

    def _claimed_names(
        self, metadata: FormatPluginMetadata
    ) -> Iterator[Tuple[str, str, Dict[str, str]]]:
        for alias in (metadata.format_id, *metadata.aliases):
            yield "alias", alias, self._alias_index
        for extension in metadata.file_extensions:
            normalized = extension[1:] if extension.startswith(".") else extension
            yield "extension", normalized.lower(), self._extension_index

    def _unindex(self, format_id: str) -> None:
        existing = self._plugins.get(format_id)
        if existing is None:
            return
        for _, name, index in self._claimed_names(existing.metadata):
            if index.get(name) == format_id:
                del index[name]


# -- module-level default registry and public conversion API ({p053}, {p054}) --

_DEFAULT_REGISTRY = FormatPluginRegistry()


def convert(
    common_model: Any,
    *,
    target_format_id: str,
    options: Optional[Mapping[str, Any]] = None,
    registry: Optional[FormatPluginRegistry] = None,
) -> Any:
    """Resolve ``target_format_id`` and run the plugin's export stage.

    Finds the registered plugin, runs ``export_from_common`` on
    ``common_model``, and returns its plugin-specific representation
    verbatim, exactly as {p053} specifies. A deliberate, documented
    exception to "backend representations stay inside the plugin" -- the
    same kind of one-purpose bridge as a plugin's own
    ``import_tree``/``export_tree`` pair ({p048}); the external
    parser/codegen library's own AST/CST type is never touched here, only
    what the plugin's translator already produced. Raises
    :class:`FormatPluginNotFoundError` when ``target_format_id`` is not
    registered; propagates ``UnsupportedTranslationError``/
    ``FormatPluginContractError`` unchanged -- never a default, never a
    dropped node.
    """

    plugin = (registry or _DEFAULT_REGISTRY).get_format_plugin(target_format_id)
    return plugin.export_from_common(common_model, dict(options or {}))


def generate_output(
    common_model: Any,
    target_format_id: str,
    options: Optional[Mapping[str, Any]] = None,
    *,
    registry: Optional[FormatPluginRegistry] = None,
) -> Any:
    """Resolve ``target_format_id`` and run export + output generation.

    Per {p054}: selects the plugin, exports to its backend representation,
    then generates final text/bytes -- for explicit export/save only, never
    after every mutation. Raises :class:`FormatPluginNotFoundError` when
    ``target_format_id`` is not registered; a plugin failure propagates
    unchanged rather than being masked.
    """

    plugin = (registry or _DEFAULT_REGISTRY).get_format_plugin(target_format_id)
    exported = plugin.export_from_common(common_model, dict(options or {}))
    return plugin.generate_output(exported, dict(options or {}))
