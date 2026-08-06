"""Mechanical enforcement of the C-001 PackageBoundary contract (requirement p003).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

This check statically scans the real ``src/tree_engine`` source tree with the
standard library :mod:`ast` module — never a substring/grep heuristic that a
comment or a docstring could fool — and enforces two independent rules:

1. Core/plugin isolation. Concrete external parser and code-generation
   libraries (``libcst``, the standard library ``ast`` module used as a
   parsing backend, ``tree_sitter``, ``tree_sitter_bsl``, ...) may be
   imported only inside concrete plugin modules under
   ``src/tree_engine/plugins/``. Every other module in the tree — that is,
   ``src/tree_engine/core/`` and everything else outside ``plugins/``
   (``query/``, ``storage/``, the package-level modules, ...) — must stay
   free of them, so the tree engine core never binds itself to one specific
   third-party syntax-tree technology.

2. Self-containment. Nothing under ``src/tree_engine/`` — core or plugin —
   may import the legacy ``ai_editor`` package, nor the surrounding
   ``mcp_proxy`` or ``code_analysis_server`` systems named by requirement
   p003. ``src/tree_engine`` must stand on its own as an independent
   package.

All compatibility framing for this check, like every other boundary and
contract check in this plan, is anchored to the immutable AI Editor CAS
baseline commit ``8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a`` (requirement
p004); the scan itself always runs against the current working tree, which
is expected to be at or descended from that baseline.

The check registers itself on the shared pipeline registry (see
``pipeline/registry.py``) and reports through ``CheckResult``/
``CheckStatus`` only — it never prints or calls ``sys.exit`` itself; the
pipeline CLI owns all console output and process exit codes.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import List, Optional, Tuple

from pipeline import registry
from pipeline.registry import CheckResult

CHECK_NAME = "check-boundary-check"
CHECK_DESCRIPTION = (
    "Mechanically enforce the C-001 PackageBoundary contract: core stays free "
    "of concrete parser/codegen libraries (reserved to plugins), and "
    "src/tree_engine never imports ai_editor, mcp_proxy, or "
    "code_analysis_server."
)

# Baseline commit anchoring all compatibility framing for this check (p004).
# The check scans the live working tree; this constant documents the pinned
# reference the scan is expected to be consistent with, it is not itself a
# git query.
BASELINE_COMMIT = "8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a"

# Path to the package this check governs, relative to the repository root.
TREE_ENGINE_RELATIVE = Path("src") / "tree_engine"

# Immediate child directory name of tree_engine that holds concrete format
# plugins; only modules under this directory are exempt from the
# parser-library rule.
PLUGINS_DIR_NAME = "plugins"

# Root module names of external parser/codegen libraries a specific concrete
# translator binds to. Forbidden outside src/tree_engine/plugins/.
FORBIDDEN_PARSER_LIBRARIES = frozenset(
    {
        "libcst",
        "ast",
        "tree_sitter",
        "tree_sitter_bsl",
    }
)

# Root module names of the surrounding legacy systems the package must never
# depend on, anywhere under src/tree_engine (requirement p003).
FORBIDDEN_LEGACY_PACKAGES = frozenset(
    {
        "ai_editor",
        "mcp_proxy",
        "code_analysis_server",
    }
)

_PARSER_RULE = "parser-library-outside-plugins"
_LEGACY_RULE = "legacy-package-import"
_SYNTAX_RULE = "unparsable-module"


@dataclasses.dataclass(frozen=True)
class Violation:
    """One offending import: where it is, what it names, and why it is illegal."""

    file_path: Path
    line: int
    module_name: str
    rule: str
    detail: str = ""

    def format(self, root: Path) -> str:
        try:
            rel = self.file_path.relative_to(root)
        except ValueError:
            rel = self.file_path
        head = f"{rel}:{self.line}: forbidden import {self.module_name!r} [{self.rule}]"
        return f"{head} - {self.detail}" if self.detail else head


def _root_module_name(dotted_name: str) -> str:
    """Return the leftmost component of a dotted module name."""
    return dotted_name.split(".", 1)[0]


def _iter_python_files(base: Path) -> List[Path]:
    """Return every ``*.py`` file under ``base``, deterministically ordered."""
    return sorted(base.rglob("*.py"))


def _is_under_plugins(file_path: Path, tree_engine_root: Path) -> bool:
    """True when ``file_path`` lives under ``tree_engine_root/plugins/``."""
    try:
        rel_parts = file_path.relative_to(tree_engine_root).parts
    except ValueError:
        return False
    return bool(rel_parts) and rel_parts[0] == PLUGINS_DIR_NAME


def _imported_root_modules(node: ast.AST) -> List[Tuple[str, int]]:
    """Return (root_module_name, line_number) pairs named by one import node.

    Only ``ast.Import``/``ast.ImportFrom`` nodes carry import references;
    string literals in docstrings, comments, and ordinary code that merely
    mentions a library name as text are not import nodes and are never
    visited here, so they cannot trigger a false positive.
    """
    found: List[Tuple[str, int]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            found.append((_root_module_name(alias.name), node.lineno))
    elif isinstance(node, ast.ImportFrom):
        if node.module:
            found.append((_root_module_name(node.module), node.lineno))
    return found


def _scan_file(file_path: Path, tree_engine_root: Path) -> List[Violation]:
    """Scan one module's AST for boundary violations."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [Violation(file_path, 0, "<unreadable>", _SYNTAX_RULE, str(exc))]

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return [
            Violation(
                file_path,
                exc.lineno or 0,
                "<syntax-error>",
                _SYNTAX_RULE,
                exc.msg or "could not parse module",
            )
        ]

    in_plugins = _is_under_plugins(file_path, tree_engine_root)
    violations: List[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for root_name, lineno in _imported_root_modules(node):
            if root_name in FORBIDDEN_LEGACY_PACKAGES:
                violations.append(
                    Violation(
                        file_path,
                        lineno,
                        root_name,
                        _LEGACY_RULE,
                        "src/tree_engine must be self-contained (p003)",
                    )
                )
            elif root_name in FORBIDDEN_PARSER_LIBRARIES and not in_plugins:
                violations.append(
                    Violation(
                        file_path,
                        lineno,
                        root_name,
                        _PARSER_RULE,
                        "concrete parser/codegen libraries belong to a plugin "
                        "module under src/tree_engine/plugins/ (p003)",
                    )
                )
    return violations


def _scan_tree(tree_engine_root: Path) -> Tuple[List[Violation], int]:
    """Scan every module under ``tree_engine_root``; return violations and file count."""
    files = _iter_python_files(tree_engine_root)
    violations: List[Violation] = []
    for file_path in files:
        violations.extend(_scan_file(file_path, tree_engine_root))
    return violations, len(files)


def check_boundary(repo_root: Optional[Path] = None) -> CheckResult:
    """Scan the real repository and report the PackageBoundary verdict.

    ``repo_root`` defaults to the repository this file lives in (three
    directories up from ``pipeline/checks/check_boundary.py``), so the
    check runs against whatever real source tree it is shipped with,
    including a verbatim copy of the repository used for isolated testing.
    """
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[2]
    tree_engine_root = root / TREE_ENGINE_RELATIVE

    if not tree_engine_root.is_dir():
        return CheckResult.fail(
            message=f"tree_engine package not found at {tree_engine_root}",
        )

    violations, file_count = _scan_tree(tree_engine_root)

    if not violations:
        return CheckResult.ok(
            message=(
                f"no PackageBoundary violations across {file_count} module(s) "
                f"under {TREE_ENGINE_RELATIVE} (baseline {BASELINE_COMMIT[:12]})"
            ),
        )

    output = "\n".join(v.format(root) for v in violations)
    return CheckResult.fail(
        message=(
            f"{len(violations)} PackageBoundary violation(s) found under "
            f"{TREE_ENGINE_RELATIVE}"
        ),
        output=output,
    )


registry.register(CHECK_NAME, CHECK_DESCRIPTION, check_boundary)
