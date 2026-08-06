"""Reality checks for ``adapter.mcp_adapter`` (G-029/T-001/A-004, C-023).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

``MCPAdapter`` claims to be a pure translation layer: every command it
exposes must return one of exactly two envelope shapes -- a success
envelope (``success``/``command``/``format_id``/``capabilities``/``data``)
or a failure envelope (``success=False`` with ``error.code``/``message``/
``details``) -- and ``raise_for_result`` must turn a failure envelope back
into the real typed exception for its ``ErrorCode``, never a generic one.
This suite drives the adapter with real files against real, live-registered
format plugins (no mocks, no stubs): every source string below is a
genuine, independently written sample, parsed by the real engine.

Failure families are triggered for real, not asserted from documentation:
an unknown extension, an explicit but unregistered ``format_id``, content a
real parser rejects, a malformed selector, an address no live document
resolves, and a file that genuinely does not exist. Each is exercised once
against the live adapter and its envelope/``raise_for_result`` pair is
checked against the exact ``ErrorCode`` the engine module that raised it
documents for that condition (verified interactively against
``adapter/mcp_adapter.py``, ``tree_engine/plugins/selection.py``,
``tree_engine/plugins/registry.py``, ``tree_engine/plugins/python/plugin.py``,
``tree_engine/query/selector.py`` and ``tree_engine/query/inspection.py``
before this file was written).

Two adapter-documented realities are pinned here so nobody mistakes them
for bugs later: node addresses are parse-local (a raw ``node_id`` minted by
one ``universal_file_open``/``universal_file_preview`` call is already
foreign to the next fresh parse of the very same file -- ``select=`` is the
only durable addressing form), and ``coverage_gaps()`` legitimately reports
matrix-``SUPPORTED`` capabilities this command surface simply does not
consume (e.g. the ``import_tree``/``export_tree`` bridge), not a defect.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from adapter.mcp_adapter import (
    COMMAND_SPECS,
    UNAVAILABLE_BASELINE_COMMANDS,
    AdapterContractError,
    CommandTrace,
    MCPAdapter,
    NOT_RECORDED,
    raise_for_result,
)
from tree_engine.exceptions import (
    FormatContentParseFailed,
    FormatPluginNotFound,
    FormatUnknownExtension,
    InvalidSelector,
    NodeNotFound,
    StorageIOError,
)
from tree_engine.errors import ErrorCode

# Real, independent per-extension samples -- not imported from any probe
# table elsewhere in the tree, so a coincidental agreement there cannot
# mask a real disagreement here.
_SOURCES: Dict[str, str] = {
    "sample.py": "def f():\n    return 1\n",
    "sample.json": '{"a": 1, "b": [1, 2, 3]}',
    "sample.yaml": "a: 1\nitems:\n  - one\n  - two\n",
    "sample.toml": 'name = "probe"\n[table]\nvalue = 1\n',
    "sample.bsl": "Процедура Проба()\nКонецПроцедуры\n",
    "sample.txt": "first line\nsecond line\n",
}
_FORMAT_OF = {
    "sample.py": "python", "sample.json": "json", "sample.yaml": "yaml",
    "sample.toml": "toml", "sample.bsl": "bsl", "sample.txt": "plain_text",
}


@pytest.fixture
def adapter() -> MCPAdapter:
    return MCPAdapter()


def _write(tmp_path: Path, filename: str) -> Path:
    path = tmp_path / filename
    path.write_text(_SOURCES[filename], encoding="utf-8")
    return path


# -- success envelope shape --------------------------------------------------

def test_open_success_envelope_has_the_documented_shape(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    result = adapter.universal_file_open(str(path))
    assert set(result) == {"success", "command", "format_id", "capabilities", "data"}
    assert result["success"] is True
    assert result["command"] == "universal_file_open"
    assert result["format_id"] == "python"
    assert result["capabilities"] == {"parse_document": "supported"}
    assert result["data"]["node_count"] > 0
    assert result["data"]["root"]["node_id"] and result["data"]["root"]["short_id"] is not None


@pytest.mark.parametrize("filename", sorted(_SOURCES))
def test_open_succeeds_for_every_registered_format(tmp_path, adapter, filename):
    # test_all_matrix_commands_callable: every real, live-registered format
    # plugin must open through the adapter with baseline-shaped parameters.
    path = _write(tmp_path, filename)
    result = adapter.universal_file_open(str(path))
    assert result["success"] is True
    assert result["format_id"] == _FORMAT_OF[filename]
    assert result["data"]["node_count"] > 0


def test_preview_search_capabilities_all_share_the_success_shape(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    preview = adapter.universal_file_preview(str(path), select="function", depth=0)
    search = adapter.universal_file_search(str(path), query="*")
    caps = adapter.universal_file_capabilities(format_id="python")
    for command, result in (
        ("universal_file_preview", preview),
        ("universal_file_search", search),
        ("universal_file_capabilities", caps),
    ):
        assert set(result) == {"success", "command", "format_id", "capabilities", "data"}
        assert result["success"] is True
        assert result["command"] == command
        assert isinstance(result["capabilities"], dict)
    assert preview["data"]["outline"]["nodes"], "select='function' must resolve to a real node"
    assert search["data"]["total"] >= 1
    assert caps["data"]["formats"]["python"]


# -- failure envelope shape ---------------------------------------------------

def test_failure_envelope_has_the_documented_shape(tmp_path, adapter):
    missing = tmp_path / "does_not_exist.py"
    result = adapter.universal_file_open(str(missing))
    assert result["success"] is False
    assert result["command"] == "universal_file_open"
    assert set(result) == {"success", "command", "error"}
    error = result["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == ErrorCode.STORAGE_IO_ERROR.value
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], dict)


# -- raise_for_result: real failure -> real typed exception + real code -----

def test_raise_for_result_reconstructs_storage_io_error_for_a_missing_file(tmp_path, adapter):
    missing = tmp_path / "missing.py"
    result = adapter.universal_file_open(str(missing))
    with pytest.raises(StorageIOError) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.STORAGE_IO_ERROR


def test_raise_for_result_reconstructs_format_unknown_extension(tmp_path, adapter):
    path = tmp_path / "sample.no_such_ext"
    path.write_text("hello", encoding="utf-8")
    result = adapter.universal_file_open(str(path))
    with pytest.raises(FormatUnknownExtension) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.FORMAT_UNKNOWN_EXTENSION


def test_raise_for_result_reconstructs_format_plugin_not_found(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    result = adapter.universal_file_open(str(path), format_id="no_such_format_id")
    with pytest.raises(FormatPluginNotFound) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.FORMAT_PLUGIN_NOT_FOUND


def test_raise_for_result_reconstructs_format_content_parse_failed(tmp_path, adapter):
    path = tmp_path / "broken.py"
    path.write_text("def f(:\n", encoding="utf-8")  # genuinely invalid Python
    result = adapter.universal_file_open(str(path))
    with pytest.raises(FormatContentParseFailed) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.FORMAT_CONTENT_PARSE_FAILED


def test_raise_for_result_reconstructs_invalid_selector(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    result = adapter.universal_file_preview(str(path), select="((bad selector")
    with pytest.raises(InvalidSelector) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.INVALID_SELECTOR


def test_raise_for_result_reconstructs_node_not_found_for_an_unknown_address(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    result = adapter.universal_file_preview(str(path), address="not-a-real-address")
    with pytest.raises(NodeNotFound) as excinfo:
        raise_for_result(result)
    assert excinfo.value.code is ErrorCode.NODE_NOT_FOUND


def test_raise_for_result_passes_success_through_unchanged(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    result = adapter.universal_file_open(str(path))
    assert raise_for_result(result) is result


# -- unknown command / unknown parameter: contract error, never bare TypeError

def test_dispatch_on_an_unknown_command_raises_adapter_contract_error(adapter):
    with pytest.raises(AdapterContractError):
        adapter.dispatch("no_such_command", {})


def test_command_for_on_an_unknown_command_raises_adapter_contract_error(adapter):
    with pytest.raises(AdapterContractError):
        adapter.command_for("no_such_command")


def test_dispatch_with_an_unknown_parameter_raises_adapter_contract_error_not_type_error(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    with pytest.raises(AdapterContractError):
        adapter.dispatch("universal_file_open", {"file_path": str(path), "bogus_param": 1})


def test_dispatch_with_a_missing_required_parameter_raises_adapter_contract_error(adapter):
    with pytest.raises(AdapterContractError):
        adapter.dispatch("universal_file_open", {})


# -- byte fidelity through universal_file_write, no residue left behind -----

@pytest.mark.parametrize("filename", sorted(_SOURCES))
def test_write_round_trips_byte_identically_with_no_residue(tmp_path, adapter, filename):
    source_path = _write(tmp_path, filename)
    target_path = tmp_path / f"out_{filename}"
    result = adapter.universal_file_write(
        str(source_path), target_path=str(target_path), content=_SOURCES[filename])
    assert result["success"] is True
    data = result["data"]
    assert data["byte_identical"] is True
    assert data["bytes_written"] == len(_SOURCES[filename].encode("utf-8"))
    assert target_path.read_bytes() == _SOURCES[filename].encode("utf-8")
    # No journal/temp/backup sibling of either the source or the target
    # survives a successful publish: only the two real files remain.
    leftovers = {p.name for p in tmp_path.iterdir()} - {filename, f"out_{filename}"}
    assert leftovers == set(), f"residue left behind: {leftovers}"


def test_write_failure_leaves_no_journal_temp_or_backup_either(tmp_path, adapter):
    # A write whose *source* cannot be resolved must fail before any
    # storage.file_txn temp/journal file is ever created.
    result = adapter.universal_file_write(
        str(tmp_path / "missing.py"), target_path=str(tmp_path / "out.py"))
    assert result["success"] is False
    assert list(tmp_path.iterdir()) == []


# -- node addresses are parse-local: pin the reality, not a bug -------------

def test_raw_node_addresses_do_not_survive_a_second_stateless_parse(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    first = adapter.universal_file_open(str(path))
    second = adapter.universal_file_open(str(path))
    assert first["data"]["root"]["node_id"] != second["data"]["root"]["node_id"], (
        "node_id is minted fresh per parse; two independent opens of the "
        "same file must not agree on it"
    )
    stale_address = first["data"]["root"]["node_id"]
    stale_lookup = adapter.universal_file_preview(str(path), address=stale_address)
    assert stale_lookup["success"] is False
    assert stale_lookup["error"]["code"] == ErrorCode.NODE_NOT_FOUND.value


def test_select_is_the_durable_addressing_form_across_stateless_calls(tmp_path, adapter):
    path = _write(tmp_path, "sample.py")
    first = adapter.universal_file_preview(str(path), select="function", depth=0)
    second = adapter.universal_file_preview(str(path), select="function", depth=0)
    assert first["success"] is True and second["success"] is True
    assert first["data"]["outline"]["nodes"][0]["type"] == "python:FunctionDef"
    assert second["data"]["outline"]["nodes"][0]["type"] == "python:FunctionDef"


# -- coverage_gaps(): SUPPORTED capabilities this surface legitimately skips

def test_coverage_gaps_only_reports_capabilities_the_surface_really_does_not_consume(adapter):
    implemented = adapter.implemented_capabilities()
    gaps = adapter.coverage_gaps()
    assert gaps, "the adapter intentionally consumes only a subset of the matrix"
    consumed = {cap for caps in implemented.values() for cap in caps}
    for entry in gaps:
        assert entry.coverage.value in ("supported", "partial")
        assert entry.capability not in consumed or entry.format_id not in implemented
    # import_tree/export_tree bridge is real (compat_matrix confirms it live
    # for python) but no COMMAND_SPECS row ever asks for it -- must surface.
    assert any(e.format_id == "python" and e.capability == "import_export_tree_bridge" for e in gaps)


def test_implemented_capabilities_is_the_same_union_for_every_registered_format(adapter):
    implemented = adapter.implemented_capabilities()
    expected = tuple(sorted({c for s in COMMAND_SPECS.values() for c in s.required_capabilities}))
    assert set(implemented) == set(adapter.format_ids)
    assert all(caps == expected for caps in implemented.values())


# -- UNAVAILABLE_BASELINE_COMMANDS: real absences, each with its own reason -

def test_unavailable_baseline_commands_each_carry_a_real_reason():
    assert UNAVAILABLE_BASELINE_COMMANDS
    for name, reason in UNAVAILABLE_BASELINE_COMMANDS.items():
        assert isinstance(name, str) and name
        assert isinstance(reason, str) and len(reason) > 10
    assert not (set(UNAVAILABLE_BASELINE_COMMANDS) & set(COMMAND_SPECS)), (
        "a command cannot be both exposed and documented as unavailable"
    )


# -- NOT_RECORDED sentinel: what a matrix-absent (format_id, capability) reads as

def test_not_recorded_sentinel_is_returned_for_a_capability_absent_from_the_matrix(adapter):
    assert MCPAdapter._coverage("python", ("this_capability_does_not_exist",)) == {
        "this_capability_does_not_exist": NOT_RECORDED
    }


# -- trace_hook: the constructor-level comparison-mode hook is real, too ----

def test_trace_hook_observes_the_exact_envelope_the_caller_receives(tmp_path):
    traces = []
    hooked = MCPAdapter(trace_hook=traces.append)
    path = _write(tmp_path, "sample.py")
    result = hooked.universal_file_open(str(path))
    assert len(traces) == 1
    trace = traces[0]
    assert isinstance(trace, CommandTrace)
    assert trace.command == "universal_file_open"
    assert trace.params["file_path"] == str(path)
    assert trace.result == result
    assert trace.divergence() is None


def test_command_trace_divergence_reports_the_disagreeing_keys():
    trace = CommandTrace(
        command="universal_file_open", params={},
        result={"success": True, "format_id": "python", "data": {}},
        old_result={"success": True, "format_id": "text", "data": {}},
    )
    divergence = trace.divergence()
    assert divergence is not None
    assert divergence["keys"] == ["format_id"]
