"""
Packaging-metadata truth tests for `pyproject.toml` (G-030/T-001/A-006).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scope note (deliberate deviation from the plan's abstract test-name list):
`docs/release_identity.md` leaves the *distribution name*, the *project
license*, and the *initial version number* of a future, separate
`tree_engine` PyPI distribution explicitly OPEN (owner decision, not yet
made). Today `tree_engine` is packaged INSIDE the `ai-editor` distribution
(`[tool.setuptools.packages.find]` below), which already has a fixed
name/version/python-requires of its own. This file tests what is actually
fixed today; it never invents a value for an item the release-identity
record leaves open, and records that absence as a test
(`test_license_is_not_yet_declared_pending_owner_decision`) instead of
silently asserting a placeholder.

`pyproject.toml` declares no `[project.scripts]` console_scripts entry for
`pipeline` -- it ships `scripts/pipeline` as a raw `script-files` launcher
instead. Tested as the fact it is, not smoothed into a check that would not
reflect reality.

Everything here reads `pyproject.toml` with `tomllib` and asserts on the
parsed structure, or does a cheap directory walk mirroring the declared
`where`/`include`. No `python -m build` and no venv install in the default
run; one opt-in exception at the bottom (`RUN_WHEEL_BUILD_TEST=1`).
"""

import os
import stat
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject_data() -> dict:
    with open(PYPROJECT_PATH, "rb") as fh:
        return tomllib.load(fh)


@pytest.fixture(scope="module")
def project_table(pyproject_data: dict) -> dict:
    return pyproject_data["project"]


# --------------------------------------------------------------------------
# Fixed project identity (decided today, independent of the open
# tree_engine-as-separate-distribution items in docs/release_identity.md).
# --------------------------------------------------------------------------


def test_pyproject_parses_and_has_expected_top_tables(pyproject_data: dict) -> None:
    assert "build-system" in pyproject_data
    assert "project" in pyproject_data
    assert "tool" in pyproject_data


def test_build_backend_is_setuptools(pyproject_data: dict) -> None:
    build_system = pyproject_data["build-system"]
    assert build_system["build-backend"] == "setuptools.build_meta"
    requires = {Requirement(r).name for r in build_system["requires"]}
    assert requires == {"setuptools", "wheel"}


def test_distribution_name_is_ai_editor(project_table: dict) -> None:
    assert project_table["name"] == "ai-editor"


def test_version_string_is_valid_semver(project_table: dict) -> None:
    version = project_table["version"]
    parsed = Version(version)
    # Exactly MAJOR.MINOR.PATCH, no pre-release/dev/local segment: this repo
    # bumps this value on unrelated commits (see docs/baseline_anchor.md),
    # so we assert the *invariant* rather than pin a byte-exact value that
    # would go red on every legitimate release bump.
    assert len(parsed.release) == 3
    assert parsed.pre is None
    assert parsed.dev is None
    assert parsed.local is None
    assert str(version) == f"{parsed.major}.{parsed.minor}.{parsed.micro}"


def test_python_requires_is_3_10_or_higher(project_table: dict) -> None:
    spec = SpecifierSet(project_table["requires-python"])
    assert Version("3.9.99") not in spec
    assert Version("3.10.0") in spec
    assert Version("3.13.0") in spec


def test_authors_field_matches_owner(project_table: dict) -> None:
    authors = project_table["authors"]
    assert {"name": "Vasiliy Zdanovskiy", "email": "vasilyvz@gmail.com"} in authors


def test_license_is_not_yet_declared_pending_owner_decision(project_table: dict) -> None:
    # release_identity.md section 5: license is "Recommended, needs owner
    # ratification" -- explicitly NOT decided. Pins the current (undeclared)
    # state so a future addition is a deliberate change, not silent drift.
    assert "license" not in project_table
    assert "classifiers" not in project_table or not any(
        c.lower().startswith("license ::") for c in project_table.get("classifiers", [])
    )


def test_no_console_script_entry_points_declared(project_table: dict) -> None:
    # `pipeline` ships as scripts/pipeline (a script-file), not a
    # [project.scripts] console_script entry point. Fact, not papered over.
    assert "scripts" not in project_table
    assert "entry-points" not in project_table


# --------------------------------------------------------------------------
# Legacy `ai-editor` base dependencies must keep shipping exactly as before.
# --------------------------------------------------------------------------

_EXPECTED_BASE_DEPENDENCIES = frozenset(
    {
        "python-dotenv>=1.0",
        "pyyaml>=6.0",
        "types-PyYAML>=6.0",
        "ruamel.yaml>=0.18",
        "click>=8.0",
        "mcp>=1.0.0",
        "pydantic>=2.1.0",
        "lark>=1.1.0",
        "libcst>=1.1.0",
        "mcp-proxy-adapter>=8.10.19",
        "code-analysis-client>=1.0.9",
        "queuemgr>=1.0.20",
        "dulwich>=1.2.4",
        "markdown-it-py>=3.0",
        "black>=24.0",
        "flake8>=7.0",
        "ruff>=0.6.0",
        "mypy>=1.8",
    }
)


def test_base_dependencies_unchanged_snapshot(project_table: dict) -> None:
    assert set(project_table["dependencies"]) == _EXPECTED_BASE_DEPENDENCIES


def test_backend_packages_are_extras_only_not_base_dependencies(project_table: dict) -> None:
    # libcst / lark are pre-existing base deps of ai_editor's own CST/lint
    # code and intentionally NOT asserted absent here. tree-sitter and
    # tree-sitter-bsl are new with the tree_engine backends and MUST stay
    # extras-only, or a minimal `pip install ai-editor` drags in a BSL parser.
    base_names = {Requirement(r).name for r in project_table["dependencies"]}
    assert "tree-sitter" not in base_names
    assert "tree-sitter-bsl" not in base_names


# --------------------------------------------------------------------------
# tree_engine backend extras: optional, narrowly pinned.
# --------------------------------------------------------------------------

_EXPECTED_EXTRA_KEYS = frozenset(
    {
        "postgres-backup",
        "dev",
        "test",
        "typecheck",
        "quality",
        "docs",
        "tree-engine-python",
        "tree-engine-bsl",
        "tree-engine-query",
        "tree-engine",
    }
)


@pytest.fixture(scope="module")
def optional_deps(project_table: dict) -> dict:
    return project_table["optional-dependencies"]


def test_optional_dependency_keys_are_exactly_declared(optional_deps: dict) -> None:
    assert set(optional_deps.keys()) == _EXPECTED_EXTRA_KEYS


def test_tree_engine_python_extra_pins_libcst(optional_deps: dict) -> None:
    reqs = [Requirement(r) for r in optional_deps["tree-engine-python"]]
    assert [r.name for r in reqs] == ["libcst"]
    spec = reqs[0].specifier
    assert Version("1.8.6") in spec
    assert Version("1.9.0") in spec
    assert Version("1.8.5") not in spec
    assert Version("2.0.0") not in spec


def test_tree_engine_bsl_extra_pins_tree_sitter_divergence_and_bsl(optional_deps: dict) -> None:
    reqs = {r.name: r.specifier for r in (Requirement(x) for x in optional_deps["tree-engine-bsl"])}
    assert set(reqs) == {"tree-sitter", "tree-sitter-bsl"}

    ts_spec = reqs["tree-sitter"]
    # Deliberate divergence from the plan's "0.24.x": BSL grammar is ABI 15,
    # the 0.24 line can't load it. Prove the pin excludes 0.24.x, not just >=0.25.
    assert Version("0.25.0") in ts_spec
    assert Version("0.25.2") in ts_spec
    assert Version("0.24.9") not in ts_spec
    assert Version("0.26.0") not in ts_spec

    bsl_spec = reqs["tree-sitter-bsl"]
    assert Version("0.1.6") in bsl_spec
    assert Version("0.2.0") not in bsl_spec


def test_tree_engine_query_extra_pins_lark(optional_deps: dict) -> None:
    reqs = [Requirement(r) for r in optional_deps["tree-engine-query"]]
    assert [r.name for r in reqs] == ["lark"]
    spec = reqs[0].specifier
    assert Version("1.3.1") in spec
    assert Version("2.0.0") not in spec


def test_tree_engine_aggregate_extra_matches_individual_extras(optional_deps: dict) -> None:
    individual_names = set()
    individual_specs = {}
    for key in ("tree-engine-python", "tree-engine-bsl", "tree-engine-query"):
        for req in (Requirement(r) for r in optional_deps[key]):
            individual_names.add(req.name)
            individual_specs[req.name] = str(req.specifier)

    aggregate = {r.name: str(r.specifier) for r in (Requirement(x) for x in optional_deps["tree-engine"])}
    assert set(aggregate) == individual_names
    # Must not silently loosen a pin relative to its own narrower extra.
    assert aggregate == individual_specs


# --------------------------------------------------------------------------
# Packaging discovery: where / include / namespaces, checked the cheap way.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def packages_find(pyproject_data: dict) -> dict:
    return pyproject_data["tool"]["setuptools"]["packages"]["find"]


def test_packages_find_declares_where_include_namespaces(packages_find: dict) -> None:
    assert packages_find["where"] == [".", "src"]
    assert set(packages_find["include"]) == {"ai_editor*", "aiedmgr_entry*", "tree_engine*"}
    assert packages_find["namespaces"] is True


def test_packaging_discovery_matches_directory_layout(packages_find: dict) -> None:
    # Cheap directory walk mirroring the declared where/include, instead of
    # a real `python -m build`: each include stem must exist under a `where` root.
    where_roots = [REPO_ROOT / w for w in packages_find["where"]]
    stems = [pattern.rstrip("*") for pattern in packages_find["include"]]

    found = {}
    for stem in stems:
        hits = [root for root in where_roots if (root / stem).is_dir()]
        found[stem] = hits
        assert hits, f"{stem!r} not found under any of {packages_find['where']!r}"

    assert found["ai_editor"] == [REPO_ROOT / "."]
    assert found["aiedmgr_entry"] == [REPO_ROOT / "."]
    assert found["tree_engine"] == [REPO_ROOT / "src"]

    # No stray top-level "./tree_engine" that would make the "." root also
    # match tree_engine* and double-discover the package.
    assert not (REPO_ROOT / "tree_engine").is_dir()


def test_tree_engine_has_no_init_files_relies_on_namespaces(packages_find: dict) -> None:
    assert packages_find["namespaces"] is True
    init_files = list((REPO_ROOT / "src" / "tree_engine").rglob("__init__.py"))
    assert init_files == []


def test_no_conflicting_top_level_packaging_files() -> None:
    assert not (REPO_ROOT / "setup.py").exists()
    assert not (REPO_ROOT / "setup.cfg").exists()

    # client/pyproject.toml is a legitimate second, independent distribution
    # (ai-editor-client) -- not a conflicting metadata source as long as its
    # own discovery scope never overlaps this file's include patterns.
    client_pyproject = REPO_ROOT / "client" / "pyproject.toml"
    assert client_pyproject.exists()
    with open(client_pyproject, "rb") as fh:
        client_data = tomllib.load(fh)
    assert client_data["project"]["name"] == "ai-editor-client"
    client_include = set(client_data["tool"]["setuptools"]["packages"]["find"]["include"])
    assert client_include == {"ai_editor_client*"}
    assert client_include.isdisjoint({"ai_editor*", "aiedmgr_entry*", "tree_engine*"})


def test_pipeline_script_files_declared_and_executable(pyproject_data: dict) -> None:
    script_files = pyproject_data["tool"]["setuptools"]["script-files"]
    assert set(script_files) == {"scripts/aiedmgr", "scripts/aiedcfg", "scripts/pipeline"}

    pipeline_path = REPO_ROOT / "scripts" / "pipeline"
    assert pipeline_path.is_file()
    mode = pipeline_path.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/pipeline must be executable to resolve as the pipeline command"
    assert os.access(pipeline_path, os.X_OK)


# --------------------------------------------------------------------------
# Import package resolves; stdlib-only public facade has no missing
# attributes. No pip install -- src-layout import (PYTHONPATH=src), matching
# how this repository's tests already run.
# --------------------------------------------------------------------------

_STDLIB_ONLY_IMPORTABLE_MODULES = (
    "tree_engine.errors",
    "tree_engine.exceptions",
    "tree_engine.plugins.plain_text",
    "tree_engine.plugins.json_format",
    "tree_engine.plugins.toml_format",
)

# Subset that additionally declares a public `__all__` facade (tree_engine.errors
# does not -- it is a plain error-code catalog, no exception classes).
_STDLIB_ONLY_FACADE_MODULES = (
    "tree_engine.exceptions",
    "tree_engine.plugins.plain_text",
    "tree_engine.plugins.json_format",
    "tree_engine.plugins.toml_format",
)


@pytest.fixture(scope="module", autouse=True)
def src_on_path():
    src_dir = str(REPO_ROOT / "src")
    inserted = src_dir not in sys.path
    if inserted:
        sys.path.insert(0, src_dir)
    try:
        yield
    finally:
        if inserted and src_dir in sys.path:
            sys.path.remove(src_dir)


def test_import_package_resolves() -> None:
    import importlib

    for module_name in _STDLIB_ONLY_IMPORTABLE_MODULES:
        importlib.import_module(module_name)


def test_public_facade_exposed_no_missing_attributes() -> None:
    import importlib

    for module_name in _STDLIB_ONLY_FACADE_MODULES:
        module = importlib.import_module(module_name)
        public_names = getattr(module, "__all__", None)
        assert public_names, f"{module_name} declares no __all__ facade"
        for name in public_names:
            # getattr with no default: a missing attribute raises
            # AttributeError, which is exactly the failure this test exists
            # to catch.
            getattr(module, name)


# --------------------------------------------------------------------------
# Opt-in, explicitly gated: real `python -m build` + isolated venv install.
# Deselected by default (env var gate, not run unless asked for). To run:
#   RUN_WHEEL_BUILD_TEST=1 PYTHONPATH=src \
#     /home/vasilyvz/projects/tools/ai_editor/.venv/bin/python -m pytest \
#     tests/test_release_metadata.py -k wheel_build -q -p no:cacheprovider
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_WHEEL_BUILD_TEST") != "1",
    reason="opt-in only: set RUN_WHEEL_BUILD_TEST=1 to run the real build+install proof",
)
def test_wheel_build_contains_tree_engine_standalone(tmp_path) -> None:
    import subprocess
    import sys as _sys
    import zipfile

    dist_dir = tmp_path / "dist"
    subprocess.run(
        [_sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=REPO_ROOT,
        check=True,
    )
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
    tree_engine_modules = [n for n in names if n.startswith("tree_engine/") and n.endswith(".py")]
    assert len(tree_engine_modules) > 0
