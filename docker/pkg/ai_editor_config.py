#!/usr/bin/env python3
"""
Host-side administration CLI for the ai-editor-docker settings file.

Edits /etc/default/ai-editor through a validated argument surface and re-applies the
result: config preflight, then container recreate. Nothing is written unless every
argument of the invocation validates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_editor_settings import (  # noqa: E402
    SETTINGS,
    SETTINGS_FILE,
    SettingError,
    apply_settings,
    read_settings,
    validate_pair,
)

PREFLIGHT = Path("/usr/lib/ai-editor/config-preflight.sh")
DOCKER_RUN = Path("/usr/lib/ai-editor/docker-run.sh")

_EPILOG = """\
Examples:
  ai-editor-config list
  ai-editor-config show
  ai-editor-config get AI_EDITOR_REGISTRATION_HOST
  ai-editor-config set --registration-host mcp-proxy --registration-port 3004
  ai-editor-config set AI_EDITOR_CODE_ANALYSIS_PORT=15010 --no-apply
  ai-editor-config apply
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-editor-config",
        description="Configure the ai-editor service through /etc/default/ai-editor.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List every supported setting with its option and default")
    sub.add_parser("show", help="Show the effective settings file contents")
    sub.add_parser(
        "init",
        help="Fill any setting missing from the file with the package default "
             "(never overwrites a value that is already set)",
    )

    get_parser = sub.add_parser("get", help="Print the value of one setting")
    get_parser.add_argument("key", help="Setting name, e.g. AI_EDITOR_PORT")

    set_parser = sub.add_parser(
        "set",
        help="Validate and write settings, then re-apply them",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    for setting in SETTINGS:
        set_parser.add_argument(
            setting.option,
            dest=setting.key,
            metavar="VALUE",
            help=f"{setting.help} [{setting.key}]",
        )
    set_parser.add_argument(
        "assignments",
        nargs="*",
        metavar="KEY=VALUE",
        help="Direct assignments, e.g. AI_EDITOR_PORT=15000",
    )
    set_parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Write the settings file but do not run preflight or recreate the container",
    )

    apply_parser = sub.add_parser(
        "apply", help="Re-run the config preflight and recreate the container"
    )
    apply_parser.add_argument(
        "--check-only", action="store_true", help="Run the preflight without recreating"
    )
    return parser


def _collect_updates(args: argparse.Namespace) -> dict[str, str]:
    """Gather and validate every requested change; raise before anything is written."""
    raw: list[tuple[str, str]] = []
    for setting in SETTINGS:
        value = getattr(args, setting.key, None)
        if value is not None:
            raw.append((setting.key, value))
    for item in args.assignments:
        if "=" not in item:
            raise SettingError(f"not a KEY=VALUE assignment: {item!r}")
        key, _, value = item.partition("=")
        raw.append((key.strip(), value))

    if not raw:
        raise SettingError("no settings given; see 'ai-editor-config set --help'")

    updates: dict[str, str] = {}
    for key, value in raw:
        normalised = validate_pair(key, value)
        if key in updates and updates[key] != normalised:
            raise SettingError(f"conflicting values given for {key}")
        updates[key] = normalised
    return updates


def _run(command: list[str]) -> int:
    print(f"[ai-editor-config] running: {' '.join(command)}")
    # Flush before handing the terminal to a child, so the log reads in order.
    sys.stdout.flush()
    return subprocess.call(command)


def _apply(check_only: bool = False) -> int:
    if not PREFLIGHT.is_file():
        print(f"[ai-editor-config] preflight script missing: {PREFLIGHT}", file=sys.stderr)
        return 1
    code = _run(["bash", str(PREFLIGHT)])
    if code != 0:
        print("[ai-editor-config] preflight failed; the container was not recreated",
              file=sys.stderr)
        return code
    if check_only:
        return 0
    if not DOCKER_RUN.is_file():
        print(f"[ai-editor-config] docker-run helper missing: {DOCKER_RUN}", file=sys.stderr)
        return 1
    return _run(["bash", str(DOCKER_RUN), "recreate"])


def _cmd_list() -> int:
    current = read_settings()
    width = max(len(item.key) for item in SETTINGS)
    for setting in SETTINGS:
        value = current.get(setting.key, "<built-in default>")
        print(f"{setting.key:<{width}}  {setting.option}")
        print(f"{'':<{width}}  current: {value}")
        print(f"{'':<{width}}  {setting.help}")
        for note in setting.notes:
            print(f"{'':<{width}}  note: {note}")
    return 0


def _cmd_show() -> int:
    if not SETTINGS_FILE.is_file():
        print(f"[ai-editor-config] settings file not found: {SETTINGS_FILE}", file=sys.stderr)
        return 1
    sys.stdout.write(SETTINGS_FILE.read_text(encoding="utf-8"))
    return 0


def _cmd_init() -> int:
    """
    Backfill settings the file does not carry yet.

    The package defaults are single-sourced in settings-env.sh; the caller sources it
    first, so they arrive here through the environment. An upgrade that kept an older
    conffile is completed this way, without touching any value the operator chose.
    """
    current = read_settings()
    updates: dict[str, str] = {}
    for setting in SETTINGS:
        if setting.key in current:
            continue
        value = os.environ.get(setting.key)
        if value is None or not value.strip():
            continue
        updates[setting.key] = validate_pair(setting.key, value.strip())
    if not updates:
        print("[ai-editor-config] settings file is already complete")
        return 0
    for key in apply_settings(updates):
        print(f"[ai-editor-config] {SETTINGS_FILE}: added {key}={updates[key]}")
    return 0


def _cmd_get(key: str) -> int:
    current = read_settings()
    if key not in current:
        raise SettingError(f"{key} is not set in {SETTINGS_FILE}")
    print(current[key])
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    updates = _collect_updates(args)
    if not SETTINGS_FILE.is_file():
        raise SettingError(f"settings file not found: {SETTINGS_FILE}")
    changed = apply_settings(updates)
    if not changed:
        print("[ai-editor-config] no change: every requested value is already in place")
    for key in changed:
        print(f"[ai-editor-config] {SETTINGS_FILE}: {key}={updates[key]}")
    if args.no_apply:
        print("[ai-editor-config] --no-apply: run 'ai-editor-config apply' to activate")
        return 0
    return _apply()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return _cmd_list()
        if args.command == "show":
            return _cmd_show()
        if args.command == "init":
            return _cmd_init()
        if args.command == "get":
            return _cmd_get(args.key)
        if args.command == "set":
            return _cmd_set(args)
        if args.command == "apply":
            return _apply(check_only=args.check_only)
    except SettingError as exc:
        print(f"[ai-editor-config] REJECTED: {exc}", file=sys.stderr)
        print("[ai-editor-config] nothing was written to the settings file", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"[ai-editor-config] permission denied: {exc}", file=sys.stderr)
        print("[ai-editor-config] run as root: sudo ai-editor-config ...", file=sys.stderr)
        return 3
    print(f"[ai-editor-config] unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
