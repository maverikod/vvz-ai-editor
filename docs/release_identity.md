# Release identity decision record — `tree_engine` standalone package

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Plan: `24271419-4dc6-44f2-8613-f350310f5c12`, step G-030/T-001/A-001
(concept C-024, ReleaseAndPackaging). Scope: fix and justify the identity
of the first standalone publication of the tree-editing engine currently
developed at `src/tree_engine/` — distribution name, import package name,
license, versioning rules, supported Python versions, and repository
location. **No release of this package has ever been cut** — there is no
prior version number, no prior tag, no prior PyPI upload. Nothing below
invents one. Where the choice is genuinely the package owner's to make
(a name, a license, a first version number), this record states the
options and their consequences and leaves the final pick open rather than
deciding it silently.

Governing requirements this record answers to (source-of-truth labels from
the plan's HRS, quoted from the branch prompt for G-030/T-001/A-001):

- **{p002}**: the package is published on PyPI, installs via `pip`, uses
  semantic versioning, and ships a typed public API, documentation, and a
  changelog.
- **{p031}**: the package is developed in a **separate repository**, and CI
  builds sdist/wheel, runs tests/typecheck/lint, and publishes a
  pre-release and — on a tag, after green CI — a stable release to PyPI.
- **{p032}**: minimum Python for the first version is **3.10** (required by
  `tree-sitter-bsl`); backend dependencies are pinned to verified-compatible
  lines (LibCST 1.9.x, tree-sitter-bsl 0.1.6 with the tree-sitter 0.24.x
  branch it supports); a backend major-version bump re-triggers the
  contract/round-trip gate. **This record does not restate the dependency
  pins or the re-gate rule** — those belong to the sibling packaging-metadata
  output of T-001, not here.
- **{p041}**: the project counts as done only after a stable PyPI release,
  passing contract tests and the benchmark gate, AI Editor wired to the
  package, and the original performance defect confirmed fixed without
  functional loss.

## 1. Hard constraint: standalone distribution (decided)

The owner requirement that `tree_engine` be installable and usable
**standalone** — because it is deployed to the code-analysis server as a
preview component — is already enforced mechanically, not aspirational.
Running the boundary check against the current worktree:

```
$ PYTHONPATH=. python3 -c "
from pipeline.checks import check_boundary
r = check_boundary.check_boundary()
print(r.status, r.message)"
CheckStatus.PASS no PackageBoundary violations across 50 module(s) under
src/tree_engine (baseline 8fb05d1f4cfa)
```

`pipeline/checks/check_boundary.py` statically AST-scans every module under
`src/tree_engine/` and rejects (a) any import of `ai_editor`, `mcp_proxy`,
or `code_analysis_server` anywhere in the tree, and (b) any import of a
concrete parser/codegen library (`libcst`, `ast`, `tree_sitter`,
`tree_sitter_bsl`) outside `src/tree_engine/plugins/`. It currently passes
across all 50 modules.

Cross-checked against the actual packaging config: the repository's
existing `pyproject.toml` (`[tool.setuptools.packages.find]`,
`include = ["ai_editor*", "aiedmgr_entry*"]`) does **not** include
`src/tree_engine` in any form today — it builds no `tree_engine` package,
declares no `tree_engine` dependency, and pins none of `libcst`,
`tree_sitter`, or `tree_sitter_bsl` (only `libcst>=1.1.0` and `lark>=1.1.0`
appear, generically, for the existing `ai_editor` codebase).

**Decision**: `tree_engine` ships as its own distinct PyPI distribution,
not as a subpackage folded into the existing `ai-editor` distribution.
Given the hard zero-import boundary above, folding it into `ai-editor`'s
existing package would gain nothing (the code already refuses to depend on
`ai_editor`) and would tie the engine's release cadence to `ai-editor`'s,
defeating the stated purpose of deploying it standalone to the CAS server.
This choice is a consequence of the enforced constraint, not a preference.

There is repository precedent for this pattern: `client/pyproject.toml`
already declares a second, independent distribution (`ai-editor-client`,
import package `ai_editor_client`) built from a subdirectory of the same
monorepo, with its own `[project]` table and its own package-data. It
currently borrows `ai-editor`'s version number verbatim
(`client/ai_editor_client/version.txt` = `1.0.83`, matching
`pyproject.toml`'s `version = "1.0.83"`) — a lockstep-versioning pattern
this record explicitly does **not** propose repeating for `tree_engine`
(see §4).

## 2. Open decision: PyPI distribution name

Not decided here. Candidates, none checked for PyPI namespace availability
as part of this record (that check must happen at publication time, not be
assumed):

| Option | Rationale | Risk |
|---|---|---|
| `tree-engine` | Matches the import package and the source directory name exactly; shortest, most discoverable. | Generic term; higher chance of a name collision or an already-taken/confusable name on PyPI. |
| `ai-tree-engine` | Signals lineage from the AI Editor project without importing its name as a hard dependency. | Longer; still generic enough to collide. |
| `treeedit-engine` / `structural-tree-engine` | Emphasizes the structural-edit domain (selectors, insert/delete/replace) over generic "tree". | Less discoverable; invented compound. |

**Consequence of the choice**: the distribution name is what end users type
into `pip install`; it is independent of the import name (§3) and can
differ from it (as `ai-editor-client` already differs from
`ai_editor_client` only by the hyphen/underscore convention, not by stem).
Owner must pick one and confirm it is free on PyPI before any CI release
job references it.

## 3. Import package name (recommended, needs owner ratification)

**Recommendation: `tree_engine`.** Unlike the distribution name, this is
already a fact on the ground, not a green-field choice: every module under
`src/tree_engine/` imports its siblings through the absolute path
`tree_engine.<subpackage>...` today — for example
`storage/codec.py` does `from tree_engine.core.identity import NodeAddress`,
`from tree_engine.core.short_id import ShortIdMap, from_hex, to_hex`, and
`from tree_engine.storage.schema import ...`; `plugins/contract.py`,
`plugins/registry.py`, and the four concrete plugin modules
(`plugins/plain_text.py`, `plugins/json_format.py`, `plugins/toml_format.py`,
`plugins/bsl/plugin.py`, `plugins/python/plugin.py`) all follow the same
convention. Renaming the import root now means rewriting all 50 modules'
imports for no functional gain. It is recorded here as an open item only
because a public import name is part of the package's compatibility
surface and the owner should explicitly ratify it rather than have it
default by inertia.

One packaging fact worth flagging for the sibling packaging-metadata
output (not resolved here): `find src/tree_engine -iname "__init__.py"`
returns **no results** anywhere in the tree — every subpackage
(`core/`, `storage/`, `query/`, `plugins/`, `plugins/bsl/`,
`plugins/python/`) is currently an implicit namespace package. Standard
`setuptools.packages.find` (as `pyproject.toml` already uses for
`ai_editor`) expects regular packages with `__init__.py`; packaging
`tree_engine` as-is will need either `__init__.py` files added or
`find_namespace_packages`/`find_namespace` semantics in its build config.

## 4. Semantic versioning rules and initial version

**Decision: adopt SemVer 2.0.0** (`MAJOR.MINOR.PATCH`, pre-release and
build-metadata suffixes per the spec), per the {p002} requirement. This
answers the versioning-*rules* half of the plan's object; the initial
*number* is left open below.

**Reconciliation with the version numbers the code already commits to**
(read directly from source, not inferred):

| Artifact | Constant | Value | File |
|---|---|---|---|
| Tree-file schema | `CURRENT_SCHEMA_VERSION` | `"1.0"` (`CURRENT_SCHEMA_MAJOR=1`, `CURRENT_SCHEMA_MINOR=0`) | `src/tree_engine/storage/schema.py` |
| Tree-file schema | `SUPPORTED_SCHEMA_MAJOR_VERSIONS` | `frozenset({1})` | same |
| Tree-file schema | `MINOR_MIGRATIONS` | `{}` (empty — no minor migration has ever been needed; `1.0` is the only minor shipped under major `1`) | same |
| Codec | `CODEC_VERSION` | `"1"` | `src/tree_engine/storage/codec.py` |
| Codec | `DEFAULT_CORE_CONTRACT_VERSION` | `"1.0.0"` | same |
| Plugin contract | `contract_version` (per plugin, all five: plain_text, json_format, toml_format, bsl, python) | `"1.0.0"` everywhere | `src/tree_engine/plugins/*.py` |

These are **artifact/protocol compatibility versions**, not the package's
own release version, and this record does not conflate them. They are
already internally consistent (schema major 1, codec "1", every shipped
plugin's contract 1.0.0) and none of them has ever changed, so nothing here
is inherited into a first package version number. The reconciling rule
this record does fix: **a breaking change to `CURRENT_SCHEMA_MAJOR`, to the
`CODEC_VERSION` byte format, or to the major component of any shipped
plugin's `contract_version` is a breaking change to the package's own
public contract and must bump the package's SemVer `MAJOR`.** The converse
is not required — the package MAY bump `MAJOR` for API reasons unrelated to
these constants.

**Open decision: initial version number.** No prior release exists to
extrapolate from. Two defensible starting points, with different
consequences:

| Option | Meaning under SemVer | Consequence |
|---|---|---|
| Start at `0.1.0`, iterate `0.x` pre-`1.0` | Public API is explicitly unstable; any `0.x` release may break callers. | Matches the CI shape {p031} already describes ("publishes a pre-release, and publishes the stable release ... only on a tag after all CI checks pass") most literally — `0.x` tags *are* the pre-1.0 pre-releases, and `1.0.0` is cut once {p041}'s completion bar (stable release + contract/benchmark gates green + AI Editor integrated + performance defect confirmed fixed) is met. |
| Jump straight to `1.0.0` as the first published version, using PEP 440/SemVer pre-release identifiers (`1.0.0rc1`, `1.0.0b1`, ...) for everything before it | Signals API stability from the first stable tag. | Requires the {p041} completion bar to be fully met *before* anything is called `1.0.0`; earlier CI runs publish only pre-release-tagged builds, never an untagged `0.x` stable-looking version. |

This record does not pick between them — it is the owner's call, made
before the first CI release job is wired to a real PyPI project.

## 5. Project license

**Recommendation: MIT**, alternatives and rationale below; left open for
explicit owner sign-off because publishing under an SPDX identifier is a
legal act, even though the technical evidence points one way.

- The checked-out repository already ships `LICENSE` at its root: MIT,
  `Copyright (c) 2024 Vasiliy Zdanovskiy` (verified by reading the file).
  The existing second distribution, `ai-editor-client`, ships from the same
  repository under the same license with no separate `LICENSE` file of its
  own.
- Alternatives considered:
  - **Apache-2.0** — adds an explicit patent grant and a NOTICE mechanism;
    relevant if third-party contributions or patent exposure become a
    concern for a library embedding `tree-sitter`/`libcst` bindings. Costs:
    longer license text, a second license identity to maintain alongside
    the MIT `ai-editor` core in the same author's portfolio.
  - **BSD-3-Clause** — comparable permissiveness to MIT, adds a
    non-endorsement clause. No concrete driver for it over MIT was found in
    this repository.
- **Consequence of picking anything other than MIT**: the package would
  carry a different license than its origin repository and its sibling
  `ai-editor-client` distribution, which is a defensible but deliberate
  divergence that should be a stated choice, not a default.

## 6. Supported Python versions (decided, not open)

**Minimum Python: 3.10.** This is not an owner-discretion item — it is
already the fixed floor for the whole repository
(`pyproject.toml`: `requires-python = ">=3.10"`, verified by reading the
file) and is independently forced by the `tree-sitter-bsl` dependency,
which the plan (`{p032}`) states requires Python ≥ 3.10. `tree_engine`
inherits this floor unchanged; there is no technical or contractual reason
found in this codebase to raise or lower it for the first release.

## 7. Real dependency versions vs. what the plan states (measured)

Installed versions, read from the shared checkout's virtualenv
(`/home/vasilyvz/projects/tools/ai_editor/.venv`, the environment this
worktree's tooling actually runs against — this worktree has no
virtualenv of its own):

```
$ pip show libcst tree_sitter tree_sitter_bsl lark | grep -E "^Name|^Version"
Name: libcst          Version: 1.8.6
Name: tree-sitter     Version: 0.25.2
Name: tree-sitter-bsl Version: 0.1.6
Name: lark            Version: 1.3.1
```

Two discrepancies against the plan's stated "verified compatible" lines
(`{p032}`: "LibCST 1.9.x ... tree-sitter-bsl 0.1.6 with the ... tree-sitter
0.24.x branch it supports"):

- **tree-sitter**: the plan pins the `0.24.x` branch; what is actually
  installed and what this environment's `tree-sitter-bsl` 0.1.6 works
  against is **0.25.2**, not `0.24.x`. This is the discrepancy this task
  was explicitly briefed to record.
- **LibCST**: the plan states the verified line is `1.9.x`; what is
  actually installed here is **1.8.6**, not `1.9.x`. `pyproject.toml`
  itself only pins `libcst>=1.1.0` (no upper bound), so nothing in the
  current packaging config contradicts either number — but neither does
  today's installed environment match the plan's stated `1.9.x`.

This record does not resolve these pins — per the plan text, backend
dependency versions and the "major bump re-triggers the contract/round-trip
gate" rule belong in the packaging-metadata output of T-001, not in this
identity record. It is flagged here only because §1 of this record's brief
required recording the real, measured numbers rather than the plan's
stated ones, and the two disagree.

## 8. Repository and publication location

`{p031}` already commits the *target* state: "the package is developed in
a separate repository." That is a governing requirement already made by
whoever owns the plan, not a name this record invents — this record just
records it as a fact and flags what is not yet true of it.

**What is true today** (measured): `tree_engine` lives at
`src/tree_engine/` inside the `ai_editor` monorepo, whose `origin` remote
is `git@github.com:maverikod/vvz-ai-editor.git` (`git remote -v`, this
worktree). No extraction to a separate repository has happened; no
separate repository URL exists to record. Inventing one here would violate
this record's own no-invented-facts rule, so none is given.

**Open**: the separate-repository *name*, hosting location, and the exact
point in the plan (before or after the packaging-metadata / CI-release
steps of this same tactical step) at which the extraction happens are not
decided by this record. `client/` (a subdirectory distribution built from
the same monorepo, per §1) is the closest existing precedent for "a second
distribution can be built from a subdirectory without a full repository
split" — the owner may choose that shape instead of a literal separate
repository, but that would need to be reconciled against `{p031}`'s
explicit wording, which this record does not have standing to override.

## 9. Summary

| Identity element | Status | Value / options |
|---|---|---|
| Ships standalone from `ai-editor` | **Decided** (constraint-forced) | Yes — separate distribution; boundary check `PASS`, existing `pyproject.toml` does not package `tree_engine` |
| PyPI distribution name | **Open** | `tree-engine` / `ai-tree-engine` / `treeedit-engine` (availability unchecked) |
| Import package name | **Recommended** (needs ratification) | `tree_engine` (already used by all 50 modules) |
| License | **Recommended** (needs ratification) | MIT (matches repo `LICENSE` and `ai-editor-client`); alternatives Apache-2.0, BSD-3-Clause |
| Versioning rules | **Decided** | SemVer 2.0.0; package MAJOR bump forced by a breaking change to schema major (`1`), `CODEC_VERSION` (`"1"`), or any plugin `contract_version` major (`1.0.0`) |
| Initial version number | **Open** | Start at `0.1.0` and iterate, or start at `1.0.0` behind PEP 440 pre-release tags |
| Minimum Python | **Decided** | `>=3.10`, matches existing `pyproject.toml` and the `tree-sitter-bsl` floor |
| Repository location | **Partly decided by `{p031}`, timing/URL open** | Target: separate repository (stated by the plan); today: `src/tree_engine/` inside `git@github.com:maverikod/vvz-ai-editor.git`, no split has happened |

Downstream packaging configuration, CI/CD release workflows, and
documentation must reference these decisions, not restate or re-derive
them; open items above must be closed by the owner before the first
`pyproject.toml`/CI wiring for `tree_engine` is written.
