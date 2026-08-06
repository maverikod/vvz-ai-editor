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
``pipeline/registry.py``) before ``main()`` is called; this module never
imports check modules itself, it only reads whatever is already on the
registry. That keeps this file the single canonical runner without needing
to know what kinds of checks exist.

Migrating the legacy verification script's behaviour behind this
application (as opposed to the fresh checks registered by later work) is
explicitly out of scope for this file and is deferred to later, dedicated
steps; nothing under ``scripts/`` is imported, wrapped, or modified here.
"""

from __future__ import annotations

import argparse
import sys
from typing import IO, Optional, Sequence

from pipeline.registry import Check, CheckNotFoundError, CheckResult, Registry, get_registry

PROG = "pipeline"


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
        subparsers.add_parser(entry.name, help=entry.description or "(no description)")
    return parser


def main(argv: Optional[Sequence[str]] = None, registry: Optional[Registry] = None) -> int:
    """Entry point: parse argv against the current registry and dispatch.

    ``registry`` defaults to the process-wide singleton
    (``pipeline.registry.get_registry()``); tests may pass an isolated
    :class:`~pipeline.registry.Registry` instance instead.
    """
    registry = registry if registry is not None else get_registry()
    parser = _build_parser(registry)
    args = parser.parse_args(argv)

    if args.command is None:
        return run_all(registry)
    if args.command == "list":
        return list_registered_checks(registry)
    return run_named_check(args.command, registry)


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
