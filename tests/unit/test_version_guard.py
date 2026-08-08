"""The version rule enforced at RUNTIME, not only at packaging time.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``tests/unit/test_version_pinning.py`` guarantees that the three distributions
DECLARE one number. That is a packaging-time guarantee and it is not enough: a
wheel can be installed over another, a container can be built from a stale
layer, an old client can call a new server. None of those is visible to a test
in this repository, and all of them produce a version mismatch on the real
deployed system.

So there are three runtime enforcement points, and this file covers them:

1. **Server <-> engine, at startup.**
   `ai_editor.core.dependency_compat.assert_tree_engine_version_matches`
   refuses to let the server come up unless the INSTALLED
   ``ai-editor-tree-engine`` distribution is exactly
   `ai_editor.version.REQUIRED_TREE_ENGINE_VERSION`.
2. **Client <-> server, per call.**
   `CodeAnalysisAsyncClient._guard_server_version` refuses to dispatch to a
   server of a different version, raising
   `ai_editor_client.exceptions.ServerVersionMismatch` -- except for ``health``
   and ``info``, which stay usable precisely so the mismatch can be diagnosed.
3. **The declaration**, one constant per distribution, both derived from the
   one shared ``VERSION`` file.

Monkeypatching `importlib.metadata.version` below is a regression net, not the
proof: the proof is an actually-installed mismatched engine in a throwaway
venv, recorded in the branch's delivery report.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_editor.core import dependency_compat
from ai_editor.core.dependency_compat import (
    EngineVersionMismatch,
    assert_tree_engine_version_matches,
    installed_tree_engine_version,
)
from ai_editor.version import (
    DECLARED_VERSION,
    REQUIRED_CLIENT_VERSION,
    REQUIRED_TREE_ENGINE_VERSION,
    TREE_ENGINE_DISTRIBUTION,
    VERSION_FILE,
)
from ai_editor_client import CodeAnalysisAsyncClient, ServerVersionMismatch
from ai_editor_client import server_version as client_version_module

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_VERSION_FILE = REPO_ROOT / "VERSION"


# ---------------------------------------------------------------------------
# 3. The declaration itself.
# ---------------------------------------------------------------------------


def test_server_declaration_reads_the_one_shared_version_file() -> None:
    assert VERSION_FILE.resolve() == ROOT_VERSION_FILE.resolve()
    assert DECLARED_VERSION == ROOT_VERSION_FILE.read_text(encoding="utf-8").strip()


def test_client_declaration_reads_the_one_shared_version_file() -> None:
    assert client_version_module.VERSION_FILE.resolve() == ROOT_VERSION_FILE.resolve()
    assert (
        client_version_module.DECLARED_VERSION
        == ROOT_VERSION_FILE.read_text(encoding="utf-8").strip()
    )


def test_server_requires_exactly_its_own_version_of_engine_and_client() -> None:
    # Exact equality, never a compatible range.
    assert REQUIRED_TREE_ENGINE_VERSION == DECLARED_VERSION
    assert REQUIRED_CLIENT_VERSION == DECLARED_VERSION


def test_client_requires_exactly_its_own_version_of_the_server() -> None:
    assert (
        client_version_module.REQUIRED_SERVER_VERSION
        == client_version_module.DECLARED_VERSION
    )


def test_the_two_declarations_are_the_same_number() -> None:
    # Two declaration modules exist only because the client is a separate
    # distribution that cannot import `ai_editor`. There is still one number.
    assert client_version_module.DECLARED_VERSION == DECLARED_VERSION


def test_client_dunder_version_is_the_declaration_not_a_second_derivation() -> None:
    import ai_editor_client

    assert ai_editor_client.__version__ == client_version_module.DECLARED_VERSION


# ---------------------------------------------------------------------------
# 1. Server <-> engine.
# ---------------------------------------------------------------------------


def test_engine_guard_passes_when_the_installed_engine_is_the_declared_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependency_compat,
        "installed_tree_engine_version",
        lambda: REQUIRED_TREE_ENGINE_VERSION,
    )
    assert_tree_engine_version_matches()  # must not raise


@pytest.mark.parametrize("installed", ["1.0.92", "1.0.94", "2.0.0", "1.0.93.post1"])
def test_engine_guard_refuses_any_other_version(
    monkeypatch: pytest.MonkeyPatch, installed: str
) -> None:
    monkeypatch.setattr(
        dependency_compat, "installed_tree_engine_version", lambda: installed
    )
    with pytest.raises(EngineVersionMismatch) as excinfo:
        assert_tree_engine_version_matches()
    message = str(excinfo.value)
    # The message must name BOTH versions and the file that declares the rule.
    assert installed in message
    assert REQUIRED_TREE_ENGINE_VERSION in message
    assert str(VERSION_FILE) in message


def test_engine_guard_refuses_a_newer_engine_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Not "at least": a newer engine is refused exactly like an older one,
    # because the engine owns the on-disk tree file format.
    monkeypatch.setattr(
        dependency_compat, "installed_tree_engine_version", lambda: "9.9.9"
    )
    with pytest.raises(EngineVersionMismatch):
        assert_tree_engine_version_matches()


def test_engine_guard_refuses_when_the_distribution_metadata_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A source checkout with src/ on sys.path: `import tree_engine` works, but
    # nothing says which version it is. That is refused with the same declared
    # error, not with a confusing traceback and not by letting it through.
    def _absent(distribution: str) -> str:
        raise metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(dependency_compat.metadata, "version", _absent)
    assert installed_tree_engine_version() is None
    with pytest.raises(EngineVersionMismatch) as excinfo:
        assert_tree_engine_version_matches()
    message = str(excinfo.value)
    assert "NOT INSTALLED" in message
    assert TREE_ENGINE_DISTRIBUTION in message
    assert REQUIRED_TREE_ENGINE_VERSION in message
    assert str(VERSION_FILE) in message


def test_server_startup_calls_the_engine_guard() -> None:
    # The guard is worthless if nothing invokes it; main() must.
    from ai_editor import main as main_module

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    assert "assert_tree_engine_version_matches()" in source


# ---------------------------------------------------------------------------
# 2. Client <-> server.
# ---------------------------------------------------------------------------

CLIENT_VERSION = client_version_module.REQUIRED_SERVER_VERSION


def _rpc_for_server(version: str) -> MagicMock:
    """A mock rpc whose ``health`` reports ``version``."""
    rpc = MagicMock()

    async def _execute(command: str, params: dict, **kwargs: object) -> dict:
        if command == "health":
            return {"success": True, "data": {"status": "ok", "version": version}}
        return {"success": True, "data": {"command": command}}

    rpc.execute_command = AsyncMock(side_effect=_execute)
    rpc.execute_command_unified = AsyncMock(side_effect=_execute)
    return rpc


def _client_against(version: str) -> tuple[CodeAnalysisAsyncClient, MagicMock]:
    rpc = _rpc_for_server(version)
    with patch("ai_editor_client.client.JsonRpcClient", return_value=rpc):
        return CodeAnalysisAsyncClient(host="h", port=1), rpc


@pytest.mark.asyncio
async def test_client_accepts_a_server_of_its_own_version() -> None:
    client, rpc = _client_against(CLIENT_VERSION)
    out = await client.call("universal_file_preview", {"project_id": "p"})
    assert out == {"success": True, "data": {"command": "universal_file_preview"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("server", ["1.0.92", "1.0.94", "2.0.0"])
async def test_client_refuses_a_server_of_a_different_version(server: str) -> None:
    client, rpc = _client_against(server)
    with pytest.raises(ServerVersionMismatch) as excinfo:
        await client.call("universal_file_preview", {"project_id": "p"})
    error = excinfo.value
    assert error.server_version == server
    assert error.client_version == CLIENT_VERSION
    assert error.command == "universal_file_preview"
    assert server in str(error) and CLIENT_VERSION in str(error)
    # The command itself was never dispatched -- only the version probe was.
    assert [c.args[0] for c in rpc.execute_command.await_args_list] == ["health"]


@pytest.mark.asyncio
async def test_client_refuses_when_the_server_reports_no_version() -> None:
    # Fails closed: an unidentifiable server is refused, not assumed compatible.
    rpc = MagicMock()
    rpc.execute_command = AsyncMock(return_value={"success": True, "data": {}})
    with patch("ai_editor_client.client.JsonRpcClient", return_value=rpc):
        client = CodeAnalysisAsyncClient(host="h", port=1)
    with pytest.raises(ServerVersionMismatch) as excinfo:
        await client.call("universal_file_preview", {})
    assert excinfo.value.server_version is None


@pytest.mark.asyncio
@pytest.mark.parametrize("exempt", ["health", "info"])
async def test_health_and_info_still_work_against_a_mismatched_server(
    exempt: str,
) -> None:
    # The operational reason for the exemption: these are the commands used to
    # SEE a version mismatch, so they must not be the ones it breaks.
    client, rpc = _client_against("1.0.42")
    out = await client.call(exempt, {})
    assert out["success"] is True
    dispatched = [c.args[0] for c in rpc.execute_command.await_args_list]
    assert dispatched == [exempt]


@pytest.mark.asyncio
async def test_exempt_commands_are_exactly_health_and_info() -> None:
    assert client_version_module.VERSION_EXEMPT_COMMANDS == frozenset(
        {"health", "info"}
    )


@pytest.mark.asyncio
async def test_unified_call_is_guarded_too() -> None:
    client, rpc = _client_against("1.0.42")
    with pytest.raises(ServerVersionMismatch):
        await client.call_unified("universal_file_edit", {})
    rpc.execute_command_unified.assert_not_awaited()


@pytest.mark.asyncio
async def test_validated_call_is_guarded_before_the_schema_is_fetched() -> None:
    rpc = _rpc_for_server("1.0.42")
    rpc.help = AsyncMock()
    with patch("ai_editor_client.client.JsonRpcClient", return_value=rpc):
        client = CodeAnalysisAsyncClient(host="h", port=1)
    with pytest.raises(ServerVersionMismatch):
        await client.call_validated("universal_file_open", {"project_id": "p"})
    rpc.help.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_direct_adapter_transfer_paths_are_guarded_too(
    tmp_path: Path,
) -> None:
    # FileSessionClient.download_to_path / upload_bytes reach the adapter
    # transport directly instead of going through `call`, so they call the guard
    # explicitly. They move real file bytes; a foreign server must not see them.
    client, rpc = _client_against("1.0.42")
    rpc.download_file = AsyncMock()
    rpc.upload_file = AsyncMock()
    with pytest.warns(DeprecationWarning):
        sessions = client.file_sessions

    with pytest.raises(ServerVersionMismatch):
        await sessions.download_to_path("t-1", tmp_path / "out.bin")
    rpc.download_file.assert_not_awaited()

    staged = tmp_path / "staged.bin"
    with pytest.raises(ServerVersionMismatch):
        await sessions.upload_bytes(b"payload", filename=str(staged))
    rpc.upload_file.assert_not_awaited()
    # Refused before the temporary file was written: no residue.
    assert not staged.exists()


@pytest.mark.asyncio
async def test_the_version_probe_runs_once_per_client_instance() -> None:
    client, rpc = _client_against(CLIENT_VERSION)
    await client.call("universal_file_open", {})
    await client.call("universal_file_edit", {})
    await client.call("universal_file_close", {})
    dispatched = [c.args[0] for c in rpc.execute_command.await_args_list]
    assert dispatched.count("health") == 1
