"""One version number for three distributions -- enforced, not documented.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The owner's ruling is that the server (`ai-editor`), the client
(`ai-editor-client`) and the engine (`ai-editor-tree-engine`) always carry the
SAME version. Before this file existed they drifted ten releases apart
(`pyproject.toml` 1.0.93 against `client/ai_editor_client/version.txt` 1.0.83)
with nothing pinning them.

The mechanism is a single root `VERSION` file read by all three
`pyproject.toml` files through `[tool.setuptools.dynamic]`. setuptools refuses
to read a version file outside a distribution's own root
(``setuptools.config.expand._assert_local``), so the other two distributions
reach it through symlinks -- `src/VERSION` and
`client/ai_editor_client/version.txt`. sdist and wheel builds copy the resolved
CONTENT, so a published artifact never carries a dangling link.

These tests are modelled on
``tests/unit/test_config_templates_package.py::test_pyproject_version_matches_template``,
which genuinely fires. They go red if:

* any of the three `pyproject.toml` files stops reading the shared `VERSION`,
  or reintroduces a literal version of its own;
* any of the three version-source files stops resolving to the same bytes;
* the exact `ai-editor-tree-engine==<VERSION>` pin in the server's dependencies
  falls behind `VERSION`;
* the bundled config templates' version fields drift from `VERSION`;
* the four tree_engine backend extras stop agreeing between the server's
  `pyproject.toml` and the engine's.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]

VERSION_FILE = REPO_ROOT / "VERSION"
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"
ENGINE_PYPROJECT = REPO_ROOT / "src" / "pyproject.toml"
CLIENT_PYPROJECT = REPO_ROOT / "client" / "pyproject.toml"

ENGINE_VERSION_FILE = REPO_ROOT / "src" / "VERSION"
CLIENT_VERSION_FILE = REPO_ROOT / "client" / "ai_editor_client" / "version.txt"

ENGINE_DISTRIBUTION_NAME = "ai-editor-tree-engine"

_BACKEND_EXTRA_KEYS = (
    "tree-engine-python",
    "tree-engine-bsl",
    "tree-engine-query",
    "tree-engine",
)


def _load(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def declared_version() -> str:
    """The one number, read from the one file."""
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def _dynamic_version_file(pyproject: Path) -> str:
    data = _load(pyproject)
    assert "version" in data["project"].get("dynamic", []), (
        f"{pyproject} must declare `dynamic = [\"version\"]`"
    )
    assert "version" not in data["project"], (
        f"{pyproject} carries a literal version; the only source is {VERSION_FILE}"
    )
    return data["tool"]["setuptools"]["dynamic"]["version"]["file"]


# --------------------------------------------------------------------------
# The single source of truth itself.
# --------------------------------------------------------------------------


def test_root_version_file_holds_one_plain_release_number() -> None:
    raw = VERSION_FILE.read_text(encoding="utf-8")
    assert raw.endswith("\n"), "VERSION must end with a newline"
    assert raw.count("\n") == 1, "VERSION holds exactly one line"
    parsed = Version(raw.strip())
    assert len(parsed.release) == 3
    assert parsed.pre is None and parsed.dev is None and parsed.local is None
    assert raw.strip() == f"{parsed.major}.{parsed.minor}.{parsed.micro}"


def test_root_version_file_is_a_real_file_not_a_link() -> None:
    # The other two are links INTO this one; if this one became a link too there
    # would be no source of truth left to point at.
    assert VERSION_FILE.is_file() and not VERSION_FILE.is_symlink()


# --------------------------------------------------------------------------
# Each of the three distributions reads that file, and only that file.
# --------------------------------------------------------------------------


def test_server_reads_the_shared_version_file() -> None:
    assert _dynamic_version_file(ROOT_PYPROJECT) == "VERSION"


def test_engine_reads_the_shared_version_file() -> None:
    assert _dynamic_version_file(ENGINE_PYPROJECT) == "VERSION"
    assert ENGINE_VERSION_FILE.is_symlink(), (
        "src/VERSION must be a symlink to the root VERSION, not a copy"
    )
    assert Path(ENGINE_VERSION_FILE.readlink()) == Path("../VERSION")
    assert ENGINE_VERSION_FILE.resolve() == VERSION_FILE.resolve()


def test_client_reads_the_shared_version_file() -> None:
    assert _dynamic_version_file(CLIENT_PYPROJECT) == "ai_editor_client/version.txt"
    assert CLIENT_VERSION_FILE.is_symlink(), (
        "client/ai_editor_client/version.txt must be a symlink to the root "
        "VERSION, not a copy"
    )
    assert Path(CLIENT_VERSION_FILE.readlink()) == Path("../../VERSION")
    assert CLIENT_VERSION_FILE.resolve() == VERSION_FILE.resolve()


def test_all_three_version_sources_read_identical_bytes() -> None:
    # The assertion that would have caught the measured 1.0.93 / 1.0.83 drift,
    # stated over content rather than over link metadata, so it still fires if
    # the links are ever replaced by copies.
    root = VERSION_FILE.read_bytes()
    assert ENGINE_VERSION_FILE.read_bytes() == root
    assert CLIENT_VERSION_FILE.read_bytes() == root


# --------------------------------------------------------------------------
# The server's dependency on the engine is pinned to that same number.
# --------------------------------------------------------------------------


def _engine_requirement() -> Requirement:
    deps = _load(ROOT_PYPROJECT)["project"]["dependencies"]
    matches = [
        Requirement(d)
        for d in deps
        if Requirement(d).name == ENGINE_DISTRIBUTION_NAME
    ]
    assert len(matches) == 1, (
        f"pyproject.toml must depend on {ENGINE_DISTRIBUTION_NAME} exactly once"
    )
    return matches[0]


def test_server_depends_on_the_engine_distribution() -> None:
    assert _engine_requirement().name == ENGINE_DISTRIBUTION_NAME


def test_engine_dependency_is_pinned_to_the_declared_version() -> None:
    spec = _engine_requirement().specifier
    assert str(spec) == f"=={declared_version()}", (
        "the engine pin must be exact and equal to VERSION; the engine owns "
        "node identity and the on-disk tree file, so a mismatch is on-disk "
        "corruption, not a degraded feature"
    )
    assert Version(declared_version()) in spec


def test_engine_distribution_declares_that_name() -> None:
    assert _load(ENGINE_PYPROJECT)["project"]["name"] == ENGINE_DISTRIBUTION_NAME


# --------------------------------------------------------------------------
# The config templates echo the same number.
# --------------------------------------------------------------------------

_TEMPLATE_PATHS = (
    REPO_ROOT / "ai_editor" / "config_templates" / "ai_editor_container.json",
    REPO_ROOT / "config" / "ai_editor_container.json",
)


def test_config_templates_carry_the_declared_version() -> None:
    version = declared_version()
    for path in _TEMPLATE_PATHS:
        assert path.is_file(), path
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["server_presentation"]["version"] == version, path
        assert data["registration"]["metadata"]["version"] == version, path


def test_no_stale_literal_version_left_in_the_packaging_files() -> None:
    # A literal `version = "1.2.3"` in [project] is exactly the drift this file
    # exists to prevent; catch it as text too, in case a future edit puts it
    # somewhere tomllib would happily accept.
    for path in (ROOT_PYPROJECT, ENGINE_PYPROJECT, CLIENT_PYPROJECT):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'^version\s*=\s*"', text, re.M), path


# --------------------------------------------------------------------------
# Server and engine agree on the tree_engine backend extras.
# --------------------------------------------------------------------------


def test_backend_extras_agree_between_server_and_engine() -> None:
    root_extras = _load(ROOT_PYPROJECT)["project"]["optional-dependencies"]
    engine_extras = _load(ENGINE_PYPROJECT)["project"]["optional-dependencies"]
    for key in _BACKEND_EXTRA_KEYS:
        assert key in root_extras, key
        assert key in engine_extras, key
        assert root_extras[key] == engine_extras[key], (
            f"backend extra {key!r} differs between the server's pyproject.toml "
            f"and the engine's: {root_extras[key]} != {engine_extras[key]}"
        )


def test_engine_declares_exactly_the_four_backend_extras() -> None:
    engine_extras = _load(ENGINE_PYPROJECT)["project"]["optional-dependencies"]
    assert set(engine_extras) == set(_BACKEND_EXTRA_KEYS)
