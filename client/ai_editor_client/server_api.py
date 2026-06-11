"""
Canonical command names for the high-level client API vs the live server registry.

The generic client (:class:`CodeAnalysisAsyncClient.call`) can invoke any command
returned by server ``help``. The supported facade is :mod:`universal_file`; every
name in :data:`CLIENT_FACADE_COMMANDS` must be registered on the thin server.
:mod:`file_session` command mappings are deprecated legacy only and are not part
of the supported public surface.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Callable, Dict, FrozenSet, Tuple

# Removed from the public server surface — do not use in client facades or docs.
LEGACY_REMOVED_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_read",
        "universal_file_save",
        "universal_file_replace",
        "universal_file_delete",
        "read_project_text_file",
        "write_project_text_lines",
        "create_text_file",
        "replace_file_lines",
    }
)

# CST tree MCP workflow — modules may exist in the repo but commands are not registered.
CST_REMOVED_COMMANDS: FrozenSet[str] = frozenset(
    {
        "cst_load_file",
        "cst_save_tree",
        "cst_modify_tree",
        "cst_create_file",
        "cst_find_node",
        "cst_get_node_info",
        "cst_get_node_by_range",
        "cst_get_node_at_line",
        "cst_reload_tree",
        "cst_convert_and_save",
        "list_cst_blocks",
        "query_cst",
    }
)

FILE_SESSION_COMMANDS: FrozenSet[str] = frozenset(
    {
        "session_create",
        "session_delete",
        "session_list",
        "session_view",
        "session_open_file",
        "session_close_file",
        "session_list_file_locks",
        "subordinate_session_create",
        "subordinate_session_get",
        "subordinate_session_update",
        "subordinate_session_delete",
        "subordinate_session_list",
    }
)

TRANSFER_AND_LOCK_COMMANDS: FrozenSet[str] = frozenset(
    {
        "project_file_transfer_download_begin",
        "project_file_transfer_upload_save",
        "project_file_advisory_lock_batch",
    }
)

DEPRECATED_CLIENT_FACADE_COMMANDS: FrozenSet[str] = (
    FILE_SESSION_COMMANDS | TRANSFER_AND_LOCK_COMMANDS
)

REMOVED_COMMANDS: FrozenSet[str] = (
    LEGACY_REMOVED_COMMANDS | CST_REMOVED_COMMANDS | DEPRECATED_CLIENT_FACADE_COMMANDS
)

UNIVERSAL_FILE_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_preview",
    }
)

INFRASTRUCTURE_COMMANDS: FrozenSet[str] = frozenset({"health"})

CLIENT_FACADE_COMMANDS: FrozenSet[str] = (
    UNIVERSAL_FILE_COMMANDS | INFRASTRUCTURE_COMMANDS
)

# ``FileSessionClient`` method names for each ``FILE_SESSION_COMMANDS`` entry.
# ``session_list_file_locks`` is also used by ``assert_session_exists``.
FILE_SESSION_FACADE_METHODS: Dict[str, str] = {
    "session_create": "create_session",
    "session_delete": "delete_session",
    "session_list": "list_sessions",
    "session_view": "view_session",
    "session_open_file": "lock_file",
    "session_close_file": "unlock_file",
    "session_list_file_locks": "list_file_locks",
    "subordinate_session_create": "create_subordinate_session",
    "subordinate_session_get": "get_subordinate_session",
    "subordinate_session_update": "update_subordinate_session",
    "subordinate_session_delete": "delete_subordinate_session",
    "subordinate_session_list": "list_subordinate_sessions",
}

# Transfer / advisory-lock commands may map to more than one façade method.
TRANSFER_FACADE_METHODS: Dict[str, Tuple[str, ...]] = {
    "project_file_transfer_download_begin": ("download",),
    "project_file_transfer_upload_save": ("upload", "upload_new"),
    "project_file_advisory_lock_batch": (
        "lock_files_advisory",
        "unlock_files_advisory",
    ),
}


UNIVERSAL_FILE_FACADE_METHODS: Dict[str, str] = {
    "universal_file_open": "open",
    "universal_file_edit": "edit",
    "universal_file_write": "write",
    "universal_file_close": "close",
    "universal_file_preview": "preview",
}


def assert_universal_file_facade_complete() -> None:
    """Raise ``AssertionError`` if ``UNIVERSAL_FILE_FACADE_METHODS`` is incomplete."""
    missing_cmds = UNIVERSAL_FILE_COMMANDS - set(UNIVERSAL_FILE_FACADE_METHODS)
    extra_cmds = set(UNIVERSAL_FILE_FACADE_METHODS) - UNIVERSAL_FILE_COMMANDS
    if missing_cmds or extra_cmds:
        raise AssertionError(
            "UNIVERSAL_FILE_FACADE_METHODS out of sync with UNIVERSAL_FILE_COMMANDS: "
            f"missing={sorted(missing_cmds)!r} extra={sorted(extra_cmds)!r}"
        )
    from ai_editor_client.universal_file import UniversalFileClient

    for command, method_name in UNIVERSAL_FILE_FACADE_METHODS.items():
        if not hasattr(UniversalFileClient, method_name):
            raise AssertionError(
                f"UniversalFileClient missing method {method_name!r} "
                f"for command {command!r}"
            )


def assert_file_session_facade_complete() -> None:
    """Raise ``AssertionError`` if ``FILE_SESSION_FACADE_METHODS`` is incomplete."""
    missing_cmds = FILE_SESSION_COMMANDS - set(FILE_SESSION_FACADE_METHODS)
    extra_cmds = set(FILE_SESSION_FACADE_METHODS) - FILE_SESSION_COMMANDS
    if missing_cmds or extra_cmds:
        raise AssertionError(
            "FILE_SESSION_FACADE_METHODS out of sync with FILE_SESSION_COMMANDS: "
            f"missing={sorted(missing_cmds)!r} extra={sorted(extra_cmds)!r}"
        )
    from ai_editor_client.file_session import FileSessionClient

    for command, method_name in FILE_SESSION_FACADE_METHODS.items():
        if not hasattr(FileSessionClient, method_name):
            raise AssertionError(
                f"FileSessionClient missing method {method_name!r} for command {command!r}"
            )


def assert_transfer_facade_complete() -> None:
    """Raise ``AssertionError`` if ``TRANSFER_FACADE_METHODS`` is incomplete."""
    missing_cmds = TRANSFER_AND_LOCK_COMMANDS - set(TRANSFER_FACADE_METHODS)
    extra_cmds = set(TRANSFER_FACADE_METHODS) - TRANSFER_AND_LOCK_COMMANDS
    if missing_cmds or extra_cmds:
        raise AssertionError(
            "TRANSFER_FACADE_METHODS out of sync with TRANSFER_AND_LOCK_COMMANDS: "
            f"missing={sorted(missing_cmds)!r} extra={sorted(extra_cmds)!r}"
        )
    from ai_editor_client.file_session import FileSessionClient

    for command, method_names in TRANSFER_FACADE_METHODS.items():
        for method_name in method_names:
            if not hasattr(FileSessionClient, method_name):
                raise AssertionError(
                    f"FileSessionClient missing method {method_name!r} "
                    f"for command {command!r}"
                )


def _command_registered(get_command: Callable[[str], object], name: str) -> bool:
    try:
        get_command(name)
        return True
    except KeyError:
        return False


def assert_facade_commands_registered(get_command: Callable[[str], object]) -> None:
    """Raise ``KeyError`` if any facade command is missing from the server registry."""
    missing = [
        name
        for name in sorted(CLIENT_FACADE_COMMANDS)
        if not _command_registered(get_command, name)
    ]
    if missing:
        raise KeyError(f"Client facade commands not registered on server: {missing}")


def assert_removed_commands_absent(get_command: Callable[[str], object]) -> None:
    """Raise ``AssertionError`` if a removed command is still registered."""
    present = [
        name
        for name in sorted(REMOVED_COMMANDS)
        if _command_registered(get_command, name)
    ]
    if present:
        raise AssertionError(f"Removed commands still registered: {present}")
