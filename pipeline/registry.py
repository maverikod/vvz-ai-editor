"""Process-wide registry for named checks used by the canonical pipeline CLI.

This module defines a single, dependency-free mechanism for binding a check
name to a description and a zero-argument callable that reports pass/fail
status with captured output. It is the one place check implementers plug
into: unit, lint, type, round-trip, benchmark, package, adapter, deploy, and
live-server checks all register through the same API, with no assumption
that any given check is fast, pure, or offline. A live-server check that
talks to a deployed server and takes minutes registers exactly like a
one-millisecond unit check.

Importing this module must never trigger an implicit import of any specific
test suite, check module, or application package. Only the standard library
is imported below, so importing ``pipeline.registry`` has no side effects
beyond defining the classes and the module-level singleton registry.

The pipeline CLI is a subcommand application, one subcommand per registered
check. Each check lives in its own module and registers itself by importing
this module and nothing else — `from pipeline import registry`, then either
`@registry.check("name", "description")` on its entry point or an explicit
`registry.register("name", "description", func)` call. The registry never
imports any check module itself; discovery of check modules is the CLI's
job, not this module's. What the registry guarantees to the CLI is exactly
what a subcommand needs: a stable `name` usable as the subcommand token, a
`description` for help output, and deterministic enumeration order via
`list_checks()`/`names()` matching registration order.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import traceback
from typing import Callable, Iterator, List

# A registered check name must double as a CLI subcommand token: the pipeline
# CLI builds one subcommand per registered check, using the name verbatim as
# the token users type (e.g. `pipeline live-server`) and the description as
# its help text. Keep names to the shape argparse/click subcommands expect:
# starts with a letter, then letters/digits/hyphens/underscores, no spaces.
_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class CheckStatus(enum.Enum):
    """Outcome of running a single check."""

    PASS = "pass"
    FAIL = "fail"


@dataclasses.dataclass(frozen=True)
class CheckResult:
    """Structured outcome of a check: status, a message, and captured output."""

    status: CheckStatus
    message: str = ""
    output: str = ""

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASS

    @classmethod
    def ok(cls, message: str = "", output: str = "") -> "CheckResult":
        """Convenience constructor for a passing result."""
        return cls(CheckStatus.PASS, message, output)

    @classmethod
    def fail(cls, message: str = "", output: str = "") -> "CheckResult":
        """Convenience constructor for a failing result."""
        return cls(CheckStatus.FAIL, message, output)


# A check callable takes no arguments and returns a CheckResult. It may be a
# plain function, a bound method, a lambda, a functools.partial, or any other
# zero-argument callable object (e.g. a class instance implementing
# __call__) — the registry does not care how the result is produced, only
# that invoking it with no arguments yields a CheckResult.
CheckCallable = Callable[[], CheckResult]


class CheckNotFoundError(LookupError):
    """Raised by lookup_by_name() when no check is registered under a name."""

    def __init__(self, name: str, available: List[str]):
        if available:
            known = ", ".join(sorted(available))
            message = f"no check registered under name {name!r}; known checks: {known}"
        else:
            message = f"no check registered under name {name!r}; the registry is empty"
        super().__init__(message)
        self.name = name
        self.available = list(available)


@dataclasses.dataclass(frozen=True)
class Check:
    """A single registered check: its identity plus its zero-argument callable."""

    name: str
    description: str
    func: CheckCallable

    def run(self) -> CheckResult:
        """Invoke the check callable and return its CheckResult.

        Any exception raised by the callable itself (for example a live
        check that fails to reach a server) is converted into a failing
        CheckResult carrying the traceback as captured output, rather than
        propagating and aborting the whole run.
        """
        try:
            result = self.func()
        except Exception:  # noqa: BLE001 - convert any failure into a result
            return CheckResult(
                status=CheckStatus.FAIL,
                message=f"check {self.name!r} raised an exception",
                output=traceback.format_exc(),
            )
        if not isinstance(result, CheckResult):
            raise TypeError(
                f"check {self.name!r} must return a CheckResult, "
                f"got {type(result).__name__}"
            )
        return result


class Registry:
    """Ordered collection of named checks, keyed by unique name.

    Registration order is preserved and is what list_checks() and iteration
    report, independent of check kind (unit, lint, type, round-trip,
    benchmark, package, adapter, deploy, live-server, ...). Python dicts
    (3.7+) preserve insertion order, which this class relies on for
    deterministic enumeration.
    """

    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def register(
        self,
        name: str,
        description: str,
        func: CheckCallable,
        *,
        replace: bool = False,
    ) -> Check:
        """Explicitly register a check.

        The name must be usable verbatim as a CLI subcommand token (the
        pipeline CLI maps one subcommand per registered check onto `name`,
        with `description` as its help text). Raises ValueError if name is
        empty or not a valid token, or if a check with that name is already
        registered and replace is not True.
        """
        if not name:
            raise ValueError("check name must be a non-empty string")
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                f"check name {name!r} is not a valid subcommand token; "
                "it must start with a letter and contain only letters, "
                "digits, hyphens, and underscores"
            )
        if name in self._checks and not replace:
            raise ValueError(
                f"a check named {name!r} is already registered "
                f"(pass replace=True to override)"
            )
        entry = Check(name=name, description=description, func=func)
        self._checks[name] = entry
        return entry

    def check(self, name: str, description: str = "") -> Callable[[CheckCallable], CheckCallable]:
        """Decorator form of register(): binds the decorated function as the check."""

        def decorator(func: CheckCallable) -> CheckCallable:
            self.register(name, description, func)
            return func

        return decorator

    def lookup_by_name(self, name: str) -> Check:
        """Return the Check registered under name, or raise CheckNotFoundError."""
        try:
            return self._checks[name]
        except KeyError:
            raise CheckNotFoundError(name, self.names()) from None

    def list_checks(self) -> List[Check]:
        """Return all registered checks in registration order."""
        return list(self._checks.values())

    def names(self) -> List[str]:
        """Return all registered check names in registration order."""
        return list(self._checks.keys())

    def __iter__(self) -> Iterator[Check]:
        return iter(self._checks.values())

    def __len__(self) -> int:
        return len(self._checks)

    def __contains__(self, name: object) -> bool:
        return name in self._checks

    def clear(self) -> None:
        """Remove all registered checks. Intended for test isolation only."""
        self._checks.clear()


# Module-level singleton. All check implementers share this one instance so
# that the pipeline CLI can enumerate and look up every check regardless of
# which module registered it.
_registry = Registry()


def get_registry() -> Registry:
    """Return the process-wide Registry singleton."""
    return _registry


def register(
    name: str,
    description: str,
    func: CheckCallable,
    *,
    replace: bool = False,
) -> Check:
    """Register a check on the singleton registry. See Registry.register()."""
    return _registry.register(name, description, func, replace=replace)


def check(name: str, description: str = "") -> Callable[[CheckCallable], CheckCallable]:
    """Decorator that registers the wrapped callable on the singleton registry."""
    return _registry.check(name, description)


def list_checks() -> List[Check]:
    """List all checks registered on the singleton registry, in order."""
    return _registry.list_checks()


def lookup_by_name(name: str) -> Check:
    """Look up a check by name on the singleton registry. See Registry.lookup_by_name()."""
    return _registry.lookup_by_name(name)
