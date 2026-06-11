"""
Registry of public ``ai_editor_client`` API surface that live examples must exercise.

Each runnable example module defines ``CLIENT_API_COVERAGE`` (a ``frozenset`` of
dotted names from :data:`REQUIRED_CLIENT_API`). :func:`verify_examples_cover_client_api`
runs at the end of ``run_all_examples.py``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import FrozenSet, Iterable, Set

# ---------------------------------------------------------------------------
# Canonical public API (methods + module-level helpers exported in __init__)
# ---------------------------------------------------------------------------

REQUIRED_CLIENT_API: FrozenSet[str] = frozenset(
    {
        # config
        "config.load_server_config",
        "config.adapter_settings_from_server_config",
        "config.adapter_settings_to_jsonrpc_kwargs",
        # validation / schema
        "validation.prepare_params_for_schema",
        "validation.validate_params_against_schema",
        "server_schema.parse_schema_from_help_payload",
        "server_schema.fetch_command_schema_from_server",
        # server_api (import-time sanity)
        "server_api.assert_file_session_facade_complete",
        "server_api.assert_transfer_facade_complete",
        # exceptions (raised on live paths)
        "exceptions.SessionNotFoundError",
        # CodeAnalysisAsyncClient
        "CodeAnalysisAsyncClient.__init__",
        "CodeAnalysisAsyncClient.from_jsonrpc_kwargs",
        "CodeAnalysisAsyncClient.from_adapter_settings",
        "CodeAnalysisAsyncClient.from_server_config",
        "CodeAnalysisAsyncClient.from_server_config_path",
        "CodeAnalysisAsyncClient.rpc",
        "CodeAnalysisAsyncClient.commands",
        "CodeAnalysisAsyncClient.file_sessions",
        "CodeAnalysisAsyncClient.universal_files",
        "CodeAnalysisAsyncClient.clear_command_schema_cache",
        "CodeAnalysisAsyncClient.get_command_schema",
        "CodeAnalysisAsyncClient.call_validated",
        "CodeAnalysisAsyncClient.call_unified_validated",
        "CodeAnalysisAsyncClient.call",
        "CodeAnalysisAsyncClient.call_unified",
        "CodeAnalysisAsyncClient.close",
        "CodeAnalysisAsyncClient.__aenter__",
        "CodeAnalysisAsyncClient.__aexit__",
        # ValidatedCommandsProxy
        "ValidatedCommandsProxy.clear_schema_cache",
        "ValidatedCommandsProxy.fetch_schema",
        "ValidatedCommandsProxy.invoke",
        "ValidatedCommandsProxy.__getattr__",
        # FileSessionClient
        "FileSessionClient.create_session",
        "FileSessionClient.assert_session_exists",
        "FileSessionClient.delete_session",
        "FileSessionClient.view_session",
        "FileSessionClient.create_subordinate_session",
        "FileSessionClient.get_subordinate_session",
        "FileSessionClient.update_subordinate_session",
        "FileSessionClient.delete_subordinate_session",
        "FileSessionClient.list_subordinate_sessions",
        "FileSessionClient.list_sessions",
        "FileSessionClient.lock_file",
        "FileSessionClient.unlock_file",
        "FileSessionClient.list_file_locks",
        "FileSessionClient.lock_files_advisory",
        "FileSessionClient.unlock_files_advisory",
        "FileSessionClient.download",
        "FileSessionClient.download_to_path",
        "FileSessionClient.upload_bytes",
        "FileSessionClient.upload",
        "FileSessionClient.upload_new",
        # UniversalFileClient
        "UniversalFileClient.open",
        "UniversalFileClient.edit",
        "UniversalFileClient.write",
        "UniversalFileClient.close",
        "UniversalFileClient.preview",
    }
)

EXAMPLE_MODULE_NAMES: tuple[str, ...] = (
    "ex_config_only",
    "ex_minimal_validated",
    "run_all_examples",
    "ex_file_sessions",
    "ex_session_view_subordinates",
    "ex_universal_files",
)


def _load_example_module(examples_dir: Path, name: str):
    path = examples_dir / f"{name}.py"
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def collect_coverage_from_examples(examples_dir: Path) -> Set[str]:
    """Union of ``CLIENT_API_COVERAGE`` from every example module."""
    covered: Set[str] = set()
    for name in EXAMPLE_MODULE_NAMES:
        mod = _load_example_module(examples_dir, name)
        raw = getattr(mod, "CLIENT_API_COVERAGE", None)
        if raw is None:
            raise AssertionError(f"{name}.py must define CLIENT_API_COVERAGE frozenset")
        covered.update(str(x) for x in raw)
    return covered


def verify_examples_cover_client_api(examples_dir: Path) -> None:
    """Raise ``AssertionError`` when any :data:`REQUIRED_CLIENT_API` entry is missing."""
    covered = collect_coverage_from_examples(examples_dir)
    missing = sorted(REQUIRED_CLIENT_API - covered)
    extra = sorted(covered - REQUIRED_CLIENT_API)
    if missing:
        raise AssertionError(
            "Example scripts do not cover all client API methods:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )
    if extra:
        raise AssertionError(
            "CLIENT_API_COVERAGE contains unknown entries "
            f"(update _client_api_inventory.py): {extra!r}"
        )
