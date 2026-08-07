"""Live-server gate for the transfer command family (5 commands).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Exercises, against the REAL deployed ai-editor server over mTLS:
transfer_upload_begin, transfer_upload_status, transfer_upload_complete,
transfer_download_begin, transfer_download_status. Nothing here is mocked;
real bytes are staged and read back over the transfer session's own PUT/GET
chunk endpoints (per the commands' own descriptions: begin/status/complete
are JSON-RPC, the byte transport itself is REST-only and has no JSON-RPC
command of its own, so it is scaffolding here, not a tested surface).

Every session this check opens is driven to a terminal state (``uploaded``/
``completed``) before the check returns; there is no ``transfer_delete``
command in the declared 21-command surface, so completion -- not deletion --
is how a session is left in a clean, non-dangling state. Filenames and a
random suffix keep concurrent runs against the same shared deployment from
colliding.

Registered unconditionally: an unreachable server is a plain RED failure (see
``pipeline.live.client``; no environment gate, no skip concept).

Coverage note -- read this before trusting the numbers below: like the queue
family, ``pipeline.live.client``'s ``CommandCoverage`` reads its parameter
table from ``help(cmdname=...)``'s ``data.metadata.parameters``, which is
EMPTY for all 5 of these commands (all ``type: builtin``) -- not a gap in
this check, the same declared-surface defect already pinned for ``help``/
``health``. :const:`TRANSFER_SCHEMA_PROPERTIES` below records the REAL table
(from ``data.schema.properties``, verified empirically) for the coverage
section. Declared ``error_cases`` are equally empty; the real errors below --
``TransferSessionNotFoundError``, ``TransferChecksumMismatchError``, the
plain ``TransferError`` for a missing source file, and JSON-Schema enum/
required-parameter rejection -- are genuine, reproducible server behaviour,
just never present in the command's own declared error-case map.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import traceback
import uuid
from typing import Any, Callable, Dict, List, Tuple

from pipeline import registry
from pipeline.live.client import CommandCoverage, LiveClient, data_of, error_code, is_success, run_live_check
from pipeline.registry import CheckResult

CHECK_NAME = "check-live-transfer"
CHECK_DESCRIPTION = (
    "Live gate against the REAL deployed server: full parameter and error-case "
    "coverage for all 5 transfer_* commands (upload begin/status/complete, "
    "download begin/status), staging and reading back real bytes, completing "
    "or fully draining every session it opens.")

TRANSFER_COMMANDS = ("transfer_upload_begin", "transfer_upload_status", "transfer_upload_complete",
                      "transfer_download_begin", "transfer_download_status")

#: The REAL parameter table (from data.schema.properties, not the empty
#: data.metadata.parameters -- see module docstring), for the coverage section.
TRANSFER_SCHEMA_PROPERTIES = {
    "transfer_upload_begin": "filename, size_bytes, checksum_value, compression (enum, all "
                              "required); checksum_algorithm, chunk_size (both optional)",
    "transfer_upload_status": "transfer_id (required)",
    "transfer_upload_complete": "transfer_id (required)",
    "transfer_download_begin": "source_path, filename, compression (enum, all required); "
                                "chunk_size, job_id, correlation_id, command, "
                                "inbound_transfer_id, delete_source_on_ack (all optional)",
    "transfer_download_status": "transfer_id (required)",
}


@dataclasses.dataclass(frozen=True)
class CaseResult:
    """One named case's verdict: pass/fail plus a short human detail."""

    name: str
    passed: bool
    detail: str = ""

    def format(self) -> str:
        head = f"[{'PASS' if self.passed else 'FAIL'}] {self.name}"
        return f"{head} - {self.detail}" if self.detail else head


def _run_case(name: str, func: Callable[[], str]) -> CaseResult:
    """Run one case; an assertion or any exception becomes a failing verdict."""
    try:
        return CaseResult(name, True, func() or "ok")
    except AssertionError as exc:
        return CaseResult(name, False, f"assertion failed: {exc}")
    except Exception:  # noqa: BLE001 - any real failure is this case's failure
        return CaseResult(name, False, f"unexpected exception:\n{traceback.format_exc()}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _name(label: str) -> str:
    return f"live-check-{label}-{uuid.uuid4().hex[:10]}"


def _coverages(client: LiveClient) -> Dict[str, CommandCoverage]:
    return {name: CommandCoverage(client.command_schema(name)) for name in TRANSFER_COMMANDS}


def _call(client: LiveClient, cov: Dict[str, CommandCoverage], command: str,
          params: Dict[str, Any]) -> Dict[str, Any]:
    envelope = client.call(command, params)
    cov[command].record_call(params, envelope)
    return envelope


def _put_chunk(client: LiveClient, transfer_id: str, chunk: bytes) -> None:
    client.run(client.jsonrpc_client.upload_chunk(transfer_id, 0, chunk))


def _get_all(client: LiveClient, transfer_id: str, size: int) -> bytes:
    data, _meta = client.run(client.jsonrpc_client.download_chunk(transfer_id, 0, size))
    return data


def _case_upload_missing_required(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "transfer_upload_begin", {"filename": _name("m")})
    _require(not is_success(envelope), "transfer_upload_begin with only filename should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_upload_invalid_compression(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    params = {"filename": _name("badcomp"), "size_bytes": 1, "checksum_value": "a" * 64,
              "compression": "not_a_real_compression"}
    envelope = _call(client, cov, "transfer_upload_begin", params)
    _require(not is_success(envelope), "transfer_upload_begin with a bogus compression should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_upload_identity_roundtrip(client: LiveClient,
                                     cov: Dict[str, CommandCoverage]) -> Tuple[str, str, bytes]:
    """Full identity upload: exercises every transfer_upload_begin parameter.

    Returns ``(detail, storage_path, payload)`` -- the storage_path and exact
    payload bytes feed the download-family case below, so a real download
    source with a known expected byte string always exists.
    """
    payload = f"live pipeline identity upload payload {uuid.uuid4()}\n".encode() * 4
    digest = hashlib.sha256(payload).hexdigest()
    begin = _call(client, cov, "transfer_upload_begin",
                  {"filename": _name("identity") + ".bin", "size_bytes": len(payload),
                   "checksum_value": digest, "compression": "identity",
                   "checksum_algorithm": "sha256", "chunk_size": 65536})
    _require(is_success(begin), f"transfer_upload_begin(identity) failed: {begin!r}")
    tid = data_of(begin)["transfer_id"]
    _put_chunk(client, tid, payload)
    complete = _call(client, cov, "transfer_upload_complete", {"transfer_id": tid})
    _require(is_success(complete), f"transfer_upload_complete failed: {complete!r}")
    _require(data_of(complete).get("status") == "uploaded", f"expected status=uploaded: {complete!r}")
    status = _call(client, cov, "transfer_upload_status", {"transfer_id": tid})
    _require(is_success(status), f"transfer_upload_status failed: {status!r}")
    storage_path = data_of(status).get("storage_path")
    _require(isinstance(storage_path, str) and storage_path, f"no storage_path in status: {status!r}")
    return f"transfer_id={tid} {len(payload)} bytes uploaded and verified via status", storage_path, payload


def _case_upload_gzip_roundtrip(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    plain = f"live pipeline gzip upload payload {uuid.uuid4()}\n".encode() * 8
    digest = hashlib.sha256(plain).hexdigest()
    compressed = gzip.compress(plain)
    begin = _call(client, cov, "transfer_upload_begin",
                  {"filename": _name("gzip") + ".bin.gz", "size_bytes": len(compressed),
                   "checksum_value": digest, "compression": "gzip"})
    _require(is_success(begin), f"transfer_upload_begin(gzip) failed: {begin!r}")
    tid = data_of(begin)["transfer_id"]
    _put_chunk(client, tid, compressed)
    complete = _call(client, cov, "transfer_upload_complete", {"transfer_id": tid})
    _require(is_success(complete), f"gzip transfer_upload_complete failed: {complete!r}")
    _require(data_of(complete).get("status") == "uploaded", f"expected status=uploaded: {complete!r}")
    return f"transfer_id={tid} gzip payload uploaded ({len(compressed)} wire bytes, plaintext digest matched)"


def _case_upload_checksum_mismatch(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    payload = f"checksum mismatch probe {uuid.uuid4()}\n".encode() * 3
    digest = hashlib.sha256(payload).hexdigest()
    begin = _call(client, cov, "transfer_upload_begin",
                  {"filename": _name("mismatch") + ".bin", "size_bytes": len(payload),
                   "checksum_value": digest, "compression": "identity"})
    _require(is_success(begin), f"transfer_upload_begin failed: {begin!r}")
    tid = data_of(begin)["transfer_id"]
    wrong = b"X" + payload[1:]  # same length (so the PUT itself is accepted), different digest
    _put_chunk(client, tid, wrong)
    complete = _call(client, cov, "transfer_upload_complete", {"transfer_id": tid})
    _require(not is_success(complete), "completing with mismatched bytes should fail")
    _require(error_code(complete) == -32000, f"expected -32000, got {error_code(complete)!r}")
    data = (complete["result"].get("error") or {}).get("data", {})
    _require(data.get("error_type") == "TransferChecksumMismatchError",
            f"expected TransferChecksumMismatchError, got {data!r}")
    return f"transfer_id={tid} code={error_code(complete)} error_type=TransferChecksumMismatchError"


def _case_upload_status_unknown(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "transfer_upload_status", {"transfer_id": "tr_" + "0" * 32})
    _require(not is_success(envelope), "transfer_upload_status on an unknown id should fail")
    _require(error_code(envelope) == -32000, f"expected -32000, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_upload_complete_unknown(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "transfer_upload_complete", {"transfer_id": "tr_" + "0" * 32})
    _require(not is_success(envelope), "transfer_upload_complete on an unknown id should fail")
    _require(error_code(envelope) == -32000, f"expected -32000, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_download_full_roundtrip(client: LiveClient, cov: Dict[str, CommandCoverage],
                                   source_path: str, size: int, expected: bytes) -> str:
    """Exercises every transfer_download_begin parameter, then reads the bytes back."""
    begin = _call(client, cov, "transfer_download_begin",
                  {"source_path": source_path, "filename": _name("download") + ".bin",
                   "compression": "identity", "chunk_size": 32768, "job_id": "probe-job-1",
                   "correlation_id": "probe-correlation-1", "command": "probe-command",
                   "inbound_transfer_id": "probe-inbound", "delete_source_on_ack": False})
    _require(is_success(begin), f"transfer_download_begin failed: {begin!r}")
    tid = data_of(begin)["transfer_id"]
    status1 = _call(client, cov, "transfer_download_status", {"transfer_id": tid})
    _require(is_success(status1), f"transfer_download_status (pre-read) failed: {status1!r}")
    fetched = _get_all(client, tid, size)
    _require(fetched == expected, "downloaded bytes did not match the uploaded source file")
    status2 = _call(client, cov, "transfer_download_status", {"transfer_id": tid})
    _require(is_success(status2), f"transfer_download_status (post-read) failed: {status2!r}")
    _require(data_of(status2).get("status") == "completed", f"expected status=completed: {status2!r}")
    return f"transfer_id={tid} {size} bytes downloaded and byte-for-byte verified"


def _case_download_missing_required(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "transfer_download_begin", {"filename": _name("m")})
    _require(not is_success(envelope), "transfer_download_begin with only filename should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_download_invalid_compression(client: LiveClient, cov: Dict[str, CommandCoverage],
                                        source_path: str) -> str:
    params = {"source_path": source_path, "filename": _name("badcomp"), "compression": "zstd"}
    envelope = _call(client, cov, "transfer_download_begin", params)
    _require(not is_success(envelope), "transfer_download_begin with a bogus compression should fail")
    _require(error_code(envelope) == -32602, f"expected -32602, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_download_nonexistent_source(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    params = {"source_path": "/nonexistent/live-check/path/does-not-exist.bin",
              "filename": _name("nosrc"), "compression": "identity"}
    envelope = _call(client, cov, "transfer_download_begin", params)
    _require(not is_success(envelope), "transfer_download_begin against a missing source should fail")
    _require(error_code(envelope) == -32000, f"expected -32000, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _case_download_status_unknown(client: LiveClient, cov: Dict[str, CommandCoverage]) -> str:
    envelope = _call(client, cov, "transfer_download_status", {"transfer_id": "tr_" + "0" * 32})
    _require(not is_success(envelope), "transfer_download_status on an unknown id should fail")
    _require(error_code(envelope) == -32000, f"expected -32000, got {error_code(envelope)!r}")
    return f"code={error_code(envelope)}"


def _coverage_lines(cov: Dict[str, CommandCoverage]) -> List[str]:
    lines = ["-- coverage (help(cmdname=...) declares ZERO parameters for all 5 of these "
             "builtin commands -- see module docstring; real surface below is this check's "
             "own record, not the shared harness's) --"]
    for name in TRANSFER_COMMANDS:
        lines.append(cov[name].report().format())
        lines.append(f"    real schema.properties surface: {TRANSFER_SCHEMA_PROPERTIES[name]}")
    return lines


def _body(client: LiveClient) -> CheckResult:
    cov = _coverages(client)
    roundtrip_holder: Dict[str, Any] = {}

    def _upload_roundtrip_case() -> str:
        detail, storage_path, payload = _case_upload_identity_roundtrip(client, cov)
        roundtrip_holder["storage_path"] = storage_path
        roundtrip_holder["payload"] = payload
        return detail

    cases: List[CaseResult] = [
        _run_case("transfer_upload_begin_missing_required",
                 lambda: _case_upload_missing_required(client, cov)),
        _run_case("transfer_upload_begin_invalid_compression",
                 lambda: _case_upload_invalid_compression(client, cov)),
        _run_case("transfer_upload_identity_roundtrip", _upload_roundtrip_case),
        _run_case("transfer_upload_gzip_roundtrip", lambda: _case_upload_gzip_roundtrip(client, cov)),
        _run_case("transfer_upload_checksum_mismatch", lambda: _case_upload_checksum_mismatch(client, cov)),
        _run_case("transfer_upload_status_unknown_id", lambda: _case_upload_status_unknown(client, cov)),
        _run_case("transfer_upload_complete_unknown_id", lambda: _case_upload_complete_unknown(client, cov)),
        _run_case("transfer_download_begin_missing_required",
                 lambda: _case_download_missing_required(client, cov)),
        _run_case("transfer_download_begin_nonexistent_source",
                 lambda: _case_download_nonexistent_source(client, cov)),
        _run_case("transfer_download_status_unknown_id", lambda: _case_download_status_unknown(client, cov)),
    ]
    if "storage_path" in roundtrip_holder:
        source_path, payload = roundtrip_holder["storage_path"], roundtrip_holder["payload"]
        cases.append(_run_case("transfer_download_begin_invalid_compression",
                               lambda: _case_download_invalid_compression(client, cov, source_path)))
        cases.append(_run_case("transfer_download_full_roundtrip",
                               lambda: _case_download_full_roundtrip(
                                   client, cov, source_path, len(payload), payload)))
    else:
        cases.append(CaseResult("transfer_download_begin_invalid_compression", False,
                                 "skipped: no uploaded source_path available (upload roundtrip case failed)"))
        cases.append(CaseResult("transfer_download_full_roundtrip", False,
                                 "skipped: no uploaded source_path available (upload roundtrip case failed)"))

    lines = [c.format() for c in cases]
    lines += [""] + _coverage_lines(cov)
    lines += ["", "-- deliberately left untested (see reasons) --",
              "  transfer_upload_begin/transfer_download_begin declare no formal max size or "
              "rate limit in their schema, so large-payload and throttling behaviour are out of "
              "this check's scope (kept to small in-memory payloads to stay a fast, safe live probe)"]
    output = "\n".join(lines)
    failed = [c.name for c in cases if not c.passed]
    if failed:
        return CheckResult.fail(message=f"{len(failed)}/{len(cases)} case(s) failed: " + ", ".join(failed),
                                 output=output)
    return CheckResult.ok(message=f"{len(cases)}/{len(cases)} case(s) passed", output=output)


def check_live_transfer() -> CheckResult:
    """Run every transfer_* case against the deployed server; RED if unreachable."""
    return run_live_check(_body)


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_live_transfer)
