"""Live transport and schema-driven coverage scaffolding for pipeline checks.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Foundation for every check that talks to the REAL deployed ai-editor server over
mTLS; nothing here mocks, stubs or replays. The default target is the deployed
server at ``https://192.168.254.26:15000``, reached from wherever the check runs
(a developer machine included) with the mTLS material under the repository's own
``mtls_certificates/mtls_certificates/``. All of it is overridable through
``AI_EDITOR_LIVE_{HOST,PORT,PROTOCOL,CERT,KEY,CA_CERT,TIMEOUT}``.

``JsonRpcClient.execute_command`` funnels replies through ``_extract_result``,
which RAISES ``RuntimeError`` and discards the structured error object. Checks
must assert the server's own stable codes (verified on 1.0.84:
``result.error.code == "SESSION_NOT_FOUND"``), so :meth:`LiveClient.call` uses
the same client one layer lower, at ``jsonrpc_call``, and returns the untouched
envelope: a rejection is HTTP 200 with ``result.success`` false and a stable
string or numeric ``result.error.code``, an unknown command is HTTP 500 with the
non-JSON body ``Internal Server Error``, surfaced as ``{"transport_error":
{...}}`` rather than an invented code. So ``call`` never raises because the
server said no; it raises :class:`LiveServerUnavailable` only when the server
cannot be reached, and :func:`run_live_check` turns that into a RED check -- an
unreachable deployment is our own service failing, not a check that opts out.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pipeline.registry import CheckResult

ENV_PREFIX = "AI_EDITOR_LIVE_"
CA_ENV_PREFIX = "AI_EDITOR_CODE_ANALYSIS_"
ENV_CA_SESSION = "AI_EDITOR_LIVE_CA_SESSION"
DEFAULT_HOST, DEFAULT_PORT = "192.168.254.26", 15000
DEFAULT_PROTOCOL, DEFAULT_TIMEOUT = "https", 60.0
# Code Analysis Server on the same deployment host. Inside the container the
# real env AI_EDITOR_CODE_ANALYSIS_HOST/_PORT (casmgr:15010) overrides this;
# proxy server id code-analysis-server-vvz.
DEFAULT_CA_HOST, DEFAULT_CA_PORT = "192.168.254.26", 15010

def repository_root() -> Path:
    """The checkout owning this module: nearest ancestor holding pyproject.toml.
    Never the process CWD, so any start directory resolves the same tree."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return here.parents[2]

_CERTS = repository_root() / "mtls_certificates" / "mtls_certificates"
DEFAULT_CERT, DEFAULT_KEY = str(_CERTS / "client/ai-editor.crt"), str(_CERTS / "client/ai-editor.key")
DEFAULT_CA_CERT = str(_CERTS / "ca/ca.crt")

class LiveServerUnavailable(RuntimeError):
    """The deployed server could not be reached: a RED check, never a pass."""

class LiveSchemaError(RuntimeError):
    """The server answered, but its ``help`` reply was not a usable schema."""

@dataclasses.dataclass(frozen=True)
class LiveEndpoint:
    """Everything needed to open one mTLS JSON-RPC connection."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    protocol: str = DEFAULT_PROTOCOL
    cert: str = DEFAULT_CERT
    key: str = DEFAULT_KEY
    ca_cert: str = DEFAULT_CA_CERT
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, *, prefix: str = ENV_PREFIX,
                 default_host: str = DEFAULT_HOST,
                 default_port: int = DEFAULT_PORT) -> "LiveEndpoint":
        """Read ``<prefix>HOST/PORT/PROTOCOL/CERT/KEY/CA_CERT/TIMEOUT`` from the environment."""
        get = (os.environ if env is None else env).get
        raw = (get(prefix + "PORT", str(default_port)),
               get(prefix + "TIMEOUT", str(DEFAULT_TIMEOUT)))
        try:
            port, timeout = int(raw[0]), float(raw[1])
        except ValueError as exc:
            raise LiveServerUnavailable(
                f"invalid {prefix}PORT/{prefix}TIMEOUT {raw!r}: {exc}") from exc
        return cls(get(prefix + "HOST", default_host), port,
                   get(prefix + "PROTOCOL", DEFAULT_PROTOCOL), get(prefix + "CERT", DEFAULT_CERT),
                   get(prefix + "KEY", DEFAULT_KEY), get(prefix + "CA_CERT", DEFAULT_CA_CERT),
                   timeout)

    def describe(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"

def make_client(endpoint: Optional[LiveEndpoint] = None) -> Any:
    """Build the real ``JsonRpcClient``; a missing adapter package or certificate
    file raises :class:`LiveServerUnavailable`, which fails the calling check."""
    endpoint = endpoint if endpoint is not None else LiveEndpoint.from_env()
    try:
        from mcp_proxy_adapter.client.jsonrpc_client.client import JsonRpcClient
    except ImportError as exc:
        raise LiveServerUnavailable(f"mcp_proxy_adapter is not importable here ({exc}); "
                                    "live checks run inside the deployed container") from exc
    for label, path in (("client certificate", endpoint.cert), ("client key", endpoint.key),
                        ("CA certificate", endpoint.ca_cert)):
        if not os.path.isfile(path):
            raise LiveServerUnavailable(f"{label} for {endpoint.describe()} not found at {path}")
    return JsonRpcClient(host=endpoint.host, port=endpoint.port, protocol=endpoint.protocol,
                         check_hostname=False, timeout=endpoint.timeout, cert=endpoint.cert,
                         key=endpoint.key, ca=endpoint.ca_cert)

def result_of(envelope: Mapping[str, Any]) -> Dict[str, Any]:
    """The envelope's ``result`` object, or ``{}``."""
    value = envelope.get("result")
    return dict(value) if isinstance(value, Mapping) else {}

def data_of(envelope: Mapping[str, Any]) -> Dict[str, Any]:
    """``result.data``, or ``{}`` when absent or not an object."""
    value = result_of(envelope).get("data")
    return dict(value) if isinstance(value, Mapping) else {}

def is_success(envelope: Mapping[str, Any]) -> bool:
    """True only when the envelope carries ``result.success is True``."""
    return result_of(envelope).get("success") is True

def error_of(envelope: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """``result.error``, else top-level ``error``, else ``transport_error``, else None."""
    for candidate in (result_of(envelope).get("error"), envelope.get("error"),
                      envelope.get("transport_error")):
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return None

def error_code(envelope: Mapping[str, Any]) -> Any:
    """The error ``code`` -- stable string or numeric JSON-RPC code -- or None."""
    return (error_of(envelope) or {}).get("code")

def error_message(envelope: Mapping[str, Any]) -> Any:
    """The error ``message``, or None. A check asserting a documented failure
    usually needs both halves: the code it must match, and the text a human
    will read when it does not."""
    return (error_of(envelope) or {}).get("message")

class LiveClient:
    """Synchronous facade over the real asynchronous ``JsonRpcClient``.

    One private event loop per instance, reused for every call: the underlying
    ``httpx.AsyncClient`` is cached on the transport, bound to its creating loop.
    ``jsonrpc_client``/``run`` are public for client APIs this does not wrap."""

    def __init__(self, endpoint: Optional[LiveEndpoint] = None) -> None:
        self.endpoint = endpoint if endpoint is not None else LiveEndpoint.from_env()
        self.jsonrpc_client = make_client(self.endpoint)
        self._loop = asyncio.new_event_loop()
        self._schemas: Dict[str, "CommandSchema"] = {}

    def run(self, coro: Any) -> Any:  # drive one client coroutine on our loop
        return self._loop.run_until_complete(coro)

    def call(self, command: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Envelope verbatim: a rejection is a RESULT, not an exception."""
        return self.run(self._call(command, dict(params or {})))

    async def _call(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        try:
            envelope = await self.jsonrpc_client.jsonrpc_call(command, params)
        except httpx.HTTPStatusError as exc:
            try:
                body = exc.response.json()
            except ValueError:
                body = None
            if isinstance(body, Mapping):
                return dict(body)
            return {"transport_error": {"http_status": exc.response.status_code,
                                        "body_text": exc.response.text, "command": command}}
        except (httpx.HTTPError, OSError) as exc:
            raise LiveServerUnavailable(
                f"cannot reach {self.endpoint.describe()}: {type(exc).__name__}: {exc}") from exc
        return dict(envelope) if isinstance(envelope, Mapping) else {"result": envelope}

    def command_names(self) -> List[str]:
        """Every command name the deployed server advertises through ``help``."""
        commands = data_of(self.call("help", {})).get("commands")
        if not isinstance(commands, Mapping):
            raise LiveSchemaError("help returned no command catalog")
        return sorted(str(name) for name in commands)

    def command_schema(self, command: str) -> "CommandSchema":
        """Fetch (and cache) a command's own declared schema via ``help(cmdname=...)``."""
        if command not in self._schemas:
            self._schemas[command] = parse_command_schema(
                command, self.call("help", {"cmdname": command}))
        return self._schemas[command]

    def close(self) -> None:
        try:  # teardown must never mask a verdict
            self._loop.run_until_complete(self.jsonrpc_client.close())
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._loop.close()

@dataclasses.dataclass(frozen=True)
class ParameterSpec:
    """One declared parameter, exactly as the server describes it."""

    name: str
    type: str
    required: bool
    has_default: bool = False
    default: Any = None
    enum: Tuple[Any, ...] = ()
    description: str = ""

@dataclasses.dataclass(frozen=True)
class ErrorCase:
    """One declared error case: a STABLE code plus its documentation."""

    code: str
    description: str = ""
    message: str = ""
    solution: str = ""

@dataclasses.dataclass(frozen=True)
class CommandSchema:
    """A command's declared surface: parameter table plus ``error_cases`` map."""

    name: str
    summary: str
    parameters: Mapping[str, ParameterSpec]
    error_cases: Mapping[str, ErrorCase]
    metadata: Mapping[str, Any]

    def required_parameters(self) -> List[str]:  # the omit-one negative matrix
        return [n for n, p in self.parameters.items() if p.required]

    def format_declared_surface(self) -> str:
        """The whole declared surface as text: parameter table, then error cases."""
        lines = [f"{self.name}: {len(self.parameters)} declared parameter(s), "
                 f"{len(self.error_cases)} declared error case(s)"]
        for name, spec in self.parameters.items():
            parts = [f"type={spec.type}", "required" if spec.required else "optional"]
            parts += [f"default={spec.default!r}"] if spec.has_default else []
            parts += ["enum=" + ",".join(str(v) for v in spec.enum)] if spec.enum else []
            lines.append(f"  param {name}  " + "  ".join(parts))
        lines += [f"  error {code}  {case.description}"
                  for code, case in self.error_cases.items()]
        return "\n".join(lines)

def parse_command_schema(command: str, envelope: Mapping[str, Any]) -> CommandSchema:
    """Turn a ``help(cmdname=...)`` envelope into a :class:`CommandSchema`."""
    if not is_success(envelope):
        raise LiveSchemaError(f"help(cmdname={command!r}) did not succeed: {error_of(envelope)!r}")
    metadata = data_of(envelope).get("metadata")
    if not isinstance(metadata, Mapping):
        raise LiveSchemaError(f"help(cmdname={command!r}) carried no metadata object")
    declared, parameters, error_cases = metadata.get("parameters"), {}, {}
    for name, spec in (declared if isinstance(declared, Mapping) else {}).items():
        spec = spec if isinstance(spec, Mapping) else {}
        enum = spec.get("enum")
        parameters[str(name)] = ParameterSpec(
            name=str(name), type=str(spec.get("type", "")),
            required=bool(spec.get("required", False)), has_default="default" in spec,
            default=spec.get("default"), description=str(spec.get("description", "")),
            enum=tuple(enum) if isinstance(enum, Sequence) and not isinstance(enum, str) else ())
    cases = metadata.get("error_cases")
    for code, case in (cases if isinstance(cases, Mapping) else {}).items():
        case = case if isinstance(case, Mapping) else {}
        error_cases[str(code)] = ErrorCase(
            code=str(code), description=str(case.get("description", "")),
            message=str(case.get("message", "")), solution=str(case.get("solution", "")))
    return CommandSchema(name=str(metadata.get("name", command)),
                         summary=str(metadata.get("summary", "")), parameters=parameters,
                         error_cases=error_cases, metadata=dict(metadata))

@dataclasses.dataclass(frozen=True)
class CoverageReport:
    """What a check exercised versus what the server declares."""

    command: str
    declared_parameters: Tuple[str, ...]
    untested_parameters: Tuple[str, ...]
    declared_error_codes: Tuple[str, ...]
    untested_error_codes: Tuple[str, ...]
    unknown_parameters: Tuple[str, ...]
    unknown_error_codes: Tuple[str, ...]

    @property
    def complete(self) -> bool:
        """True only when the whole declared surface was exercised."""
        return not self.untested_parameters and not self.untested_error_codes

    def format(self) -> str:
        declared_p, declared_e = len(self.declared_parameters), len(self.declared_error_codes)
        lines = [f"coverage {self.command}: parameters "
                 f"{declared_p - len(self.untested_parameters)}/{declared_p}, error cases "
                 f"{declared_e - len(self.untested_error_codes)}/{declared_e}"]
        for label, values in (("DECLARED BUT UNTESTED parameters", self.untested_parameters),
                              ("DECLARED BUT UNTESTED error cases", self.untested_error_codes),
                              ("exercised but UNDECLARED parameters", self.unknown_parameters),
                              ("exercised but UNDECLARED error codes", self.unknown_error_codes)):
            if values:
                lines.append(f"  {label}: {', '.join(values)}")
        if self.complete and not self.unknown_parameters and not self.unknown_error_codes:
            lines.append("  full declared surface exercised")
        return "\n".join(lines)

class CommandCoverage:
    """Accumulates what a check exercised and reports the untested remainder."""

    def __init__(self, schema: CommandSchema) -> None:
        self.schema = schema
        self._parameters: set = set()
        self._errors: set = set()

    def record_parameters(self, names: Iterable[str]) -> None:
        self._parameters.update(str(name) for name in names)

    def record_errors(self, codes: Iterable[Any]) -> None:
        self._errors.update(str(code) for code in codes)

    def record_call(self, params: Mapping[str, Any], envelope: Mapping[str, Any]) -> None:
        """One real call: the parameter names sent, and any error code returned."""
        self.record_parameters(params)
        code = error_code(envelope)
        if code is not None:
            self.record_errors([code])

    def report(self) -> CoverageReport:
        params, errors = tuple(self.schema.parameters), tuple(self.schema.error_cases)
        return CoverageReport(
            command=self.schema.name, declared_parameters=params, declared_error_codes=errors,
            untested_parameters=tuple(p for p in params if p not in self._parameters),
            untested_error_codes=tuple(c for c in errors if c not in self._errors),
            unknown_parameters=tuple(sorted(self._parameters - set(params))),
            unknown_error_codes=tuple(sorted(self._errors - set(errors))))

class CaSession:
    """A REAL Code Analysis Server session, as every ``universal_file_*`` needs.

    Verified from the developer machine and in-container: CA answers at
    ``192.168.254.26:15010`` (``casmgr:15010`` in-container) over the same mTLS
    triple, and ``session_create(comment=...)``/``session_delete(session_id=...)``
    succeed. ``AI_EDITOR_LIVE_CA_SESSION`` injects an externally owned id instead
    (never deleted). None is ever invented."""

    def __init__(self, session_id: str, client: Optional[LiveClient], owned: bool) -> None:
        self.session_id, self.owned, self._client = session_id, owned, client

    @classmethod
    def acquire(cls, comment: str = "ai-editor live pipeline check",
                env: Optional[Mapping[str, str]] = None) -> "CaSession":
        injected = (os.environ if env is None else env).get(ENV_CA_SESSION, "").strip()
        if injected:
            return cls(injected, None, owned=False)
        endpoint = LiveEndpoint.from_env(env, prefix=CA_ENV_PREFIX, default_host=DEFAULT_CA_HOST,
                                         default_port=DEFAULT_CA_PORT)
        client = LiveClient(endpoint)
        try:
            envelope = client.call("session_create", {"comment": comment})
        except LiveServerUnavailable:
            client.close()
            raise
        session_id = data_of(envelope).get("session_id")
        if not is_success(envelope) or not isinstance(session_id, str) or not session_id:
            client.close()
            raise LiveServerUnavailable(
                f"CA session_create at {endpoint.describe()} yielded no session id: "
                f"{error_of(envelope) or envelope!r}")
        return cls(session_id, client, owned=True)

    def dispose(self) -> None:
        """Delete the session if this object created it; always close the client."""
        client, self._client = self._client, None
        if client is not None:
            try:
                if self.owned:
                    client.call("session_delete", {"session_id": self.session_id})
            finally:
                client.close()

    def __enter__(self) -> "CaSession":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.dispose()

def run_live_check(body: Callable[[LiveClient], CheckResult],
                   endpoint: Optional[LiveEndpoint] = None) -> CheckResult:
    """Open a live client, run ``body``, always close it. An unreachable server --
    no adapter, no certificate, refused, TLS error, timeout -- FAILS the check
    with the reason: the deployment is ours, so silence is a defect to fix."""
    client = None
    try:
        client = LiveClient(endpoint)
        return body(client)
    except LiveServerUnavailable as exc:
        return CheckResult.fail(message=f"live server unreachable: {exc}")
    finally:
        if client is not None:
            client.close()
