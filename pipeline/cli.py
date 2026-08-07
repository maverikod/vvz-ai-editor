"""Canonical pipeline console application.

This module is the single entry point through which every registered check
is run. It never hard-codes a check list: it asks
:mod:`pipeline.registry` for whatever is registered at call time and turns
that into one CLI subcommand per check, named after the check itself.

Invocation modes
-----------------

``pipeline``
    No arguments: run every registered check in registration order. Prints
    a per-check PASS/FAIL line, then a summary line, and exits non-zero if
    any check failed (zero if all passed, including the empty-registry
    case).

``pipeline <check-name>``
    Run exactly the named check and exit non-zero only if it failed. The
    available names are exactly the subcommands built from the registry, so
    an unknown name is rejected by argument parsing itself with a clear
    error message and a non-zero exit code.

``pipeline list``
    Enumerate every registered check's name and description without
    invoking any of them. Nothing registered is executed in this mode.

Check modules register themselves on the shared registry singleton (see
``pipeline/registry.py``) as an import-time side effect; nothing else ever
triggers that side effect for them, so this module is also responsible for
*discovery*: walking the real ``pipeline/checks/`` package with
``pkgutil``/``importlib`` and importing every module it finds there before
building the argparse parser. Discovery never hard-codes a check's module
name — a new file dropped into ``pipeline/checks/`` becomes a subcommand
with zero change to this file. Once discovery has run, the rest of this
module only reads whatever is on the registry; it still never imports a
specific check module by name itself.

Migrating the legacy verification script's behaviour behind this
application (as opposed to the fresh checks registered by later work) is
explicitly out of scope for this file and is deferred to later, dedicated
steps; nothing under ``scripts/`` is imported, wrapped, or modified here.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from typing import IO, List, Optional, Sequence

from pipeline.registry import Check, CheckNotFoundError, CheckResult, Registry, get_registry

PROG = "pipeline"

# Dotted path of the package that holds one module per check. Discovery
# walks this package's real directory at call time; it is the only place
# that names the checks package, and it never lists individual check
# modules by name.
CHECKS_PACKAGE = "pipeline.checks"


def _print_result(check: Check, result: CheckResult, stream: IO[str]) -> None:
    """Print a single check's outcome as one PASS/FAIL line (+ output on fail)."""
    status_word = "PASS" if result.passed else "FAIL"
    line = f"[{status_word}] {check.name}"
    if result.message:
        line += f" - {result.message}"
    print(line, file=stream)
    if not result.passed and result.output:
        print(result.output, file=stream)


def run_named_check(name: str, registry: Optional[Registry] = None, stream: IO[str] = sys.stdout) -> int:
    """Run exactly one registered check by name.

    Returns 0 if it passed, 1 if it failed, 2 if no check is registered
    under ``name`` (this last case is normally pre-empted by argument
    parsing restricting subcommands to known names, but the check is kept
    here so the function is safe to call directly).
    """
    registry = registry if registry is not None else get_registry()
    try:
        entry = registry.lookup_by_name(name)
    except CheckNotFoundError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 2
    result = entry.run()
    _print_result(entry, result, stream)
    return 0 if result.passed else 1


def run_all(registry: Optional[Registry] = None, stream: IO[str] = sys.stdout) -> int:
    """Run every registered check in registration order.

    Exits 0 only if every check passed (an empty registry counts as
    passing: there is nothing to fail). Exits 1 if at least one failed.
    """
    registry = registry if registry is not None else get_registry()
    entries = registry.list_checks()
    if not entries:
        print("no checks registered", file=stream)
        return 0
    failed = 0
    for entry in entries:
        result = entry.run()
        _print_result(entry, result, stream)
        if not result.passed:
            failed += 1
    passed = len(entries) - failed
    print(f"{passed}/{len(entries)} checks passed", file=stream)
    return 1 if failed else 0


def list_registered_checks(registry: Optional[Registry] = None, stream: IO[str] = sys.stdout) -> int:
    """Print every registered check's name and description; run nothing."""
    registry = registry if registry is not None else get_registry()
    entries = registry.list_checks()
    if not entries:
        print("no checks registered", file=stream)
        return 0
    width = max(len(entry.name) for entry in entries)
    for entry in entries:
        description = entry.description or "(no description)"
        print(f"{entry.name.ljust(width)}  {description}", file=stream)
    return 0


def discover_checks(package_name: str = CHECKS_PACKAGE, stream: IO[str] = sys.stderr) -> List[str]:
    """Import every module under ``package_name`` so each check registers itself.

    A check module registers on the shared registry as an import-time side
    effect (see ``pipeline/checks/check_boundary.py``: the ``register()``
    call at the bottom of the file). Nothing else ever imports these
    modules, so this function is what makes discovery real: it walks the
    actual ``pipeline/checks/`` directory with ``pkgutil.iter_modules`` and
    imports whatever ``*.py`` files it finds there. Nothing here is a
    hand-maintained list of check names — a check file that lands in that
    directory later becomes a subcommand automatically, with zero change
    to this module.

    ``pipeline`` and ``pipeline.checks`` are plain implicit namespace
    packages (no ``__init__.py``); ``importlib``/``pkgutil`` resolve those
    the same way as regular packages; no package markers are needed for
    discovery to work.

    A module that fails to import (syntax error, a bad top-level import, a
    duplicate-name registration, ...) must not take the rest of the CLI
    down with it: the failure is caught here, reported as one warning line
    on ``stream``, and discovery continues with the next module. The dotted
    names of modules that failed to import are returned (mainly so tests
    can assert on them); this failure is deliberately kept out of the
    process exit code — a check that failed to *load* never became a
    registered check in the first place, so it cannot fail *run*, and a
    broken check file must never be able to make ``list`` or an unrelated
    check's subcommand exit non-zero.
    """
    failed: List[str] = []
    try:
        package = importlib.import_module(package_name)
    except ImportError as exc:
        print(f"{PROG}: warning: could not import package {package_name!r}: {exc}", file=stream)
        return failed

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        # Resolved to a plain module, not a package; nothing to walk.
        return failed

    for module_info in pkgutil.iter_modules(package_path, prefix=f"{package_name}."):
        if module_info.ispkg:
            continue
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:  # noqa: BLE001 - a bad check must not crash the CLI
            print(
                f"{PROG}: warning: failed to import check module {module_info.name!r}: {exc}",
                file=stream,
            )
            failed.append(module_info.name)
    return failed


def _build_parser(registry: Registry) -> argparse.ArgumentParser:
    """Build the argparse parser with one subcommand per registered check.

    The subcommand list is read from ``registry`` at call time — nothing
    here is a hard-coded check name. A dedicated ``list`` subcommand is
    added alongside the check subcommands to enumerate them without
    running anything.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Canonical pipeline check runner. With no subcommand, "
        "runs every registered check in registration order.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{list,<check-name>}")
    subparsers.add_parser("list", help="List registered check names and descriptions; run nothing.")
    for entry in registry.list_checks():
        # argparse runs help text through %-formatting, so a literal percent in a
        # check's description (a tolerance, a pass rate) makes it raise and takes
        # the WHOLE cli down, not just that check. Escape before handing it over.
        help_text = (entry.description or "(no description)").replace("%", "%%")
        subparsers.add_parser(entry.name, help=help_text)
    return parser


def main(argv: Optional[Sequence[str]] = None, registry: Optional[Registry] = None) -> int:
    """Entry point: discover checks, parse argv against the registry, dispatch.

    ``registry`` defaults to the process-wide singleton
    (``pipeline.registry.get_registry()``); tests may pass an isolated
    :class:`~pipeline.registry.Registry` instance instead. Discovery (see
    ``discover_checks()``) only runs against the real ``pipeline/checks/``
    package when the default singleton registry is in play — a caller that
    supplies its own ``Registry`` is doing test isolation and populates it
    explicitly, so real filesystem discovery is skipped for it.
    """
    using_default_registry = registry is None
    registry = registry if registry is not None else get_registry()
    if using_default_registry:
        discover_checks()
    parser = _build_parser(registry)
    args = parser.parse_args(argv)

    if args.command is None:
        return run_all(registry)
    if args.command == "list":
        return list_registered_checks(registry)
    return run_named_check(args.command, registry)


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
