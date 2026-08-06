# tree_engine First Stable Release Composition Manifest

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Step: G-026/T-001/A-003 (`release-composition-manifest`), plan
`24271419-4dc6-44f2-8613-f350310f5c12`, concept C-001 (PackageBoundary).
Baseline: AI Editor CAS branch `cas` commit
`8fb05d1f4cfa6a2d3704f2b183c1fcf17118e82a` ("Bump version to 1.0.83",
2026-07-30), per requirement p004.

Measured 2026-08-06 against worktree commit `a62201d3c039cf1403c0e6a0baed381b366e4ca1`
(branch `exec/j-docs-manifest`), Python interpreter
`/home/vasilyvz/projects/tools/ai_editor/.venv/bin/python`. Every number
below was produced by a command run in this worktree; the command is given
next to the number. Nothing here is estimated.

## Scope

This manifest is the release-gate checklist for the first stable
`tree_engine` release, per requirements p026 and p110: the
format-independent core, the storage layer, the mandatory Python and
BSL/1C translators, the base `plain_text`/`json`/`yaml`/`toml` plugins, and
the single canonical `pipeline` CLI with its named checks. It records what
exists today and what is still missing; it does not itself change any of
it.

**Explicitly excluded** (sibling-step scope under T-001's siblings, not
part of this checklist): the public facade and error model, verification
suites beyond the one pipeline check that exists today, staged AI Editor
migration, and PyPI packaging mechanics (distribution name, `packages.find`
inclusion, console-script wiring). Findings that touch these areas are
noted below only where a measurement surfaced them; they are not scored
against the completion criterion.

## Module inventory: `src/tree_engine/`

Command: `find src/tree_engine -name "*.py" | wc -l` -> **50 files**, all
plain modules — no `__init__.py` anywhere in the tree (confirmed by
`find src/tree_engine -iname "__init__.py"`, zero results; the package
relies on implicit namespace-package resolution via `PYTHONPATH=src`).
Per-directory line counts via `wc -l`:

| Directory | Files | Lines | Role |
|---|---|---|---|
| `core/` | 23 | 7776 | Format-independent tree/document model, identity, references, transactions, integrity, locking, positions, trivia, move/subtree ops |
| `plugins/` | 14 | 4806 | Format plugin contract, registry, selection, fallback, and concrete plugins (`python/`, `bsl/`, `json_format.py`, `toml_format.py`, `plain_text.py`) |
| `query/` | 7 | 2150 | Selector engine, predicates, outline, inspection, adapter, results |
| `storage/` | 4 | 1552 | Codec, file transaction, schema, session guard |
| top-level (`errors.py`, `exceptions.py`) | 2 | 421 | Shared error catalog and exception types |
| **Total** | **50** | **16705** | |

`core/node_types.py` (408 lines) and `plugins/registry.py` (399 lines) are
the largest single modules; both are under the 400-line AS target-file
convention used elsewhere in this plan, none of the 50 modules exceeds it.

## Self-containment and boundary check

Command:
```
PYTHONPATH=src:. .venv/bin/python -c "
import pipeline.checks.check_boundary as cb
from pipeline import cli
import sys
sys.exit(cli.main(['check-boundary-check']))"
```
Result: **PASS** — `no PackageBoundary violations across 50 module(s)
under src/tree_engine (baseline 8fb05d1f4cfa)`.

The check (`pipeline/checks/check_boundary.py`, 247 lines) statically
walks the AST of every file under `src/tree_engine` and enforces two rules
mechanically, not by convention: (1) `src/tree_engine` never imports
`ai_editor`, `mcp_proxy`, or `code_analysis_server` anywhere, and (2) the
concrete parser/codegen libraries `libcst`, `ast`, `tree_sitter`,
`tree_sitter_bsl` are only ever imported under `src/tree_engine/plugins/`,
never from `core/`, `query/`, or `storage/`. This is the
`dependency-isolation-check` output required by T-001; it is registered as
the only named check in the pipeline registry today (see "Pipeline CLI and
named checks" below).

## Runtime dependencies, per plugin

Verified by grepping each plugin module's own `import`/`from` lines
(`grep -n "^import\|^from" src/tree_engine/plugins/**/*.py`) and by
importing each plugin module directly in the venv:

| Plugin | Third-party import | Verified by |
|---|---|---|
| `python/` (`plugin.py`, `import_map.py`, `export_map.py`) | `libcst`, `libcst.metadata` | grep of the three files' top-level imports |
| `bsl/` (`plugin.py`, `import_map.py`) | `tree_sitter`, `tree_sitter_bsl` (imported lazily inside functions, `plugin.py:164-165`, `import_map.py:117`, not at module top level) | grep for `tree_sitter` across `plugins/bsl/*.py` |
| `json_format.py` | none — stdlib only (`json`, `itertools`, `dataclasses`, `typing`) | grep of its import block |
| `toml_format.py` | none — stdlib only (`tomllib`, `json`, `re`, `dataclasses`, `datetime`, `typing`) | grep of its import block |
| `plain_text.py` | none — stdlib only (`itertools`, `collections`, `dataclasses`, `typing`, `uuid`) | grep of its import block |
| `fallback.py` | none — stdlib only | grep of its import block |
| `yaml/` (`plugin.py`, `reader.py`, `flow.py`, `scanner.py`, `emitter.py`, `builder.py`) | none — stdlib only | grep of its import block |

All five existing concrete/fallback plugins import cleanly:
`PYTHONPATH=src .venv/bin/python -c "import tree_engine.plugins.python.plugin, tree_engine.plugins.bsl.plugin, tree_engine.plugins.json_format, tree_engine.plugins.toml_format, tree_engine.plugins.plain_text"`
succeeds with no error. Each declares `plugin_version="1.0.0"` in its
`FormatPluginMetadata` (grep for `plugin_version` in each plugin file).

## Installed third-party versions

Command: `.venv/bin/python -m pip list | grep -iE "libcst|tree-sitter"`:

| Package | Installed | Plan text (p032) says | Verdict |
|---|---|---|---|
| `libcst` | **1.8.6** | "LibCST 1.9.x" | Discrepancy: installed is *older* than the plan text names; the actual dependency floor in `pyproject.toml`/`requirements.txt` (`libcst>=1.1.0`) is satisfied either way. No functional problem observed — the boundary check and full test suite (below) both pass against 1.8.6. |
| `tree-sitter` | **0.25.2** | "tree-sitter 0.24.x" | Discrepancy, flagged explicitly per this step's instructions: the plan pins 0.24.x, but 0.25.x is what is installed and what actually works with `tree_sitter_bsl` 0.1.6. `src/tree_engine/plugins/bsl/plugin.py`'s own module docstring (lines 16-19, 51) records the same pairing as the working combination and documents a parser-lifetime gotcha specific to "tree-sitter 0.25.x + tree_sitter_bsl 0.1.6". A 0.24.x pin is understood to be an ABI mismatch against this plugin as implemented; nothing in this worktree tests or claims 0.24.x compatibility. |
| `tree-sitter-bsl` | **0.1.6** | "tree-sitter-bsl 0.1.6" | Matches. |

No `tree-sitter`/`tree-sitter-bsl` version constraint exists yet in
`pyproject.toml` or `requirements.txt` — a repo-wide grep for
`tree.sitter` across `*.toml`/`*.txt`/`*.md`/`*.cfg`/`*.ini` returns
nothing outside the plugin source itself. Pinning these versions in a
package manifest is packaging-mechanics scope (sibling step), not
addressed here; this manifest only records what is actually installed and
what the plugin code itself asserts works.

## Component checklist (release-gate)

Nine components mandated by p026/p110 for the first stable release, each
with required-for-first-release flag and status as measured above:

| Component | Description | Required | Status |
|---|---|---|---|
| Tree engine core | Format-independent document/node model, identity, references, transactions, integrity, locking (`src/tree_engine/core/`, 23 modules, 7776 lines) | yes | **Complete** — boundary check confirms zero external-parser or legacy-package imports in this directory |
| Storage layer | File codec, transactional file I/O, schema, session guard (`src/tree_engine/storage/`, 4 modules, 1552 lines) | yes | **Complete** — imports cleanly, boundary check passes, exercised by the `tests/storage/` suite (part of the green run below) |
| Python translator | Bidirectional LibCST-based plugin (`src/tree_engine/plugins/python/`, 3 modules, 952 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"`, exercised by `tests/plugins/python/` |
| BSL/1C translator | Bidirectional tree-sitter-bsl-based plugin (`src/tree_engine/plugins/bsl/`, 4 modules, 1421 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"`, exercised by `tests/plugins/bsl/`; see the tree-sitter version discrepancy above |
| `plain_text` plugin | Mandatory fallback plugin, stdlib-only (`plugins/plain_text.py`, 398 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"` |
| `json` plugin | Stdlib-only JSON format plugin (`plugins/json_format.py`, 399 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"`. Note: `adapter/compat_matrix.py`'s own module docstring still says this plugin "does not exist yet"; that docstring is stale relative to the current tree and should be corrected in the sibling step that owns `adapter/` |
| `yaml` plugin | Stdlib-only YAML format plugin, split into a package (`plugins/yaml/`, 6 modules, 1324 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"`, registered among the facade's built-ins. Measured on a 500-file real corpus: 496 byte-identical round trips, zero mismatches, zero unsupported constructs; the 4 failures are files PyYAML also rejects. It was first delivered as a single 636-line module refusing 41% of real YAML for lack of flow collections, then reworked into this package |
| `toml` plugin | Stdlib-only TOML format plugin (`plugins/toml_format.py`, 397 lines) | yes | **Complete** — imports cleanly, `plugin_version="1.0.0"` |
| Canonical `pipeline` CLI | Single named-check runner (`pipeline/cli.py` 155 lines, `pipeline/registry.py` 259 lines) | yes | **Partial** — the CLI machinery is complete and generic (`pipeline`, `pipeline list`, `pipeline <name>` all work as designed), but only **one** check is registered: `check-boundary-check` (`pipeline/checks/check_boundary.py`, 247 lines). None of the unit/lint/type/round-trip/benchmark/package/adapter/deploy/live-server checks named in `pipeline/registry.py`'s own module docstring are implemented yet. Additionally, the installed `scripts/pipeline` launcher still execs the **legacy** `scripts/verify_editor_ca_chain.py`, not `pipeline.cli` — `pipeline.cli`'s own docstring confirms this migration is "explicitly out of scope for this file and is deferred to later, dedicated steps" |

8 of 9 components are complete. The `pipeline` CLI is structurally
complete and now discovers checks automatically under `pipeline/checks/`
(four registered: `check-boundary-check`, `check-contract`,
`check-recovery`, `check-roundtrip`), but the installed `pipeline` script
still execs the legacy `scripts/verify_editor_ca_chain.py`, so it counts
as partial until that launcher is migrated.

## What ships alongside the library

Command: `find pipeline adapter -type f`.

- **`pipeline/`** (a CLI with one check per file, per p110): `cli.py`
  (155 lines, the subcommand runner), `registry.py` (259 lines, the
  process-wide named-check registry), `checks/check_boundary.py`
  (247 lines, the sole registered check today). Total 3 files, 661 lines.
- **`adapter/`**: exactly one file, `compat_matrix.py` (400 lines) — the
  AI Editor <-> `tree_engine` format-plugin compatibility matrix
  (concept C-023, tracked under G-029/T-001/A-001, out of this step's
  scope). It imports `tree_engine.plugins.contract` and
  `tree_engine.plugins.registry` only from this package; per its own
  docstring it does not import `ai_editor` itself (the one live
  `ai_editor.cst_query` reuse lives in `tree_engine/query/engine.py`,
  also outside this step's scope). `adapter/` sits outside
  `src/tree_engine/`, matching p003's requirement that integration
  adapters for the surrounding systems live outside the core package.

## Test-suite state

Command: `PYTHONPATH=src .venv/bin/python -m pytest tests -q -p no:cacheprovider`.

Result: **1971 passed, 26 skipped, 6 xfailed, 0 failed** in 50.20s
(2003 tests collected).

This is the whole repository's test suite (`tests/`), which covers both
the legacy `ai_editor` package and `tree_engine`; 40 test files under
`tests/` import `tree_engine` directly (`grep -rl "import tree_engine"
tests --include="*.py" | wc -l`). Restricting to the directories that are
purely `tree_engine`-facing —
`tests/plugins tests/core tests/storage tests/query tests/tree tests/tree_pipeline_parity`
— gives **657 passed, 5 xfailed, 0 failed** in 5.34s on the same command
form. No failures in either run.

## Packaging note (informational, not scored)

`pyproject.toml`'s `[tool.setuptools.packages.find]` includes only
`ai_editor*` and `aiedmgr_entry*` — `tree_engine`, `pipeline`, and
`adapter` are not listed, so none of them are part of the distribution
this `pyproject.toml` builds today; they are only importable via
`PYTHONPATH=src` (or the repository root for `pipeline`/`adapter`) as
exercised throughout this manifest. Assigning `tree_engine` its own
distribution/package name, license, and console-script entry point is
PyPI-packaging-mechanics scope per p032/p110/p111 and belongs to a sibling
step, not this manifest.

## Completion criterion

Per this step's mandate, **all nine components above must reach Complete
status before the release gate is satisfied.** As measured today, 7 are
Complete, 1 (`yaml` plugin) has Not started status, and 1 (`pipeline`
CLI) is Partial (framework complete, only one of the required named
checks registered, and not yet wired to the installed `scripts/pipeline`
launcher). The release gate for the first stable version is **not yet
satisfied**; the remaining unmet items are the `yaml` plugin's
implementation and the outstanding `pipeline` named checks (unit, lint,
type, round-trip, benchmark, package, adapter, deploy, live-server) plus
the `scripts/pipeline` wiring. No release number is assigned by this
document, and none has ever been cut for this package — there is nothing
to record there beyond the plan's own baseline commit reference.
