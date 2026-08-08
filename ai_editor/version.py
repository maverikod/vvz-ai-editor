"""THE VERSION DECLARATION of this build of the ai-editor server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The owner's ruling is that the server (``ai-editor``), the client
(``ai-editor-client``) and the engine (``ai-editor-tree-engine``) always carry
the SAME version, and that the rule is enforced by the CODE, not only by tests:
"if the server and client versions differ -- an error. There must be a
declaration."

This module is that declaration for the server distribution. Open this one file
to see what this build is and what it demands of the engine it runs against.
Nothing else in ``ai_editor`` may re-derive a version by string-munging a
``pyproject.toml``, by parsing a filename, or by hard-coding a literal; every
enforcement point imports the constants below.

Where the number comes from
---------------------------

``ai_editor/VERSION`` is a symlink to the repository-root ``VERSION`` file --
the single source of truth also read, through their own symlinks, by
``src/pyproject.toml`` (the engine) and ``client/ai_editor_client/version.txt``
(the client). setuptools refuses to read a version file outside a
distribution's own root (``setuptools.config.expand._assert_local``), which is
why each distribution reaches the one file through a link of its own. sdist and
wheel builds copy the RESOLVED CONTENT, so an installed wheel carries a real
file here, never a dangling link.

Reading it at import time -- rather than calling
``importlib.metadata.version("ai-editor")`` -- is deliberate. Distribution
metadata records what was written into ``*.dist-info`` when the package was
INSTALLED; an editable install left in place across a version bump reports a
stale number indefinitely. The bytes next to this module are what this build
actually IS.

Failure policy
--------------

If the declaration cannot be read, this module raises at import. That is
intentional and it fails CLOSED: a build that cannot say which version it is
cannot be allowed to decide that some other component matches it.
"""

from __future__ import annotations

from pathlib import Path

# The declaration file itself, shipped as package data (see
# `[tool.setuptools.package-data]` in the repository-root pyproject.toml).
VERSION_FILE: Path = Path(__file__).resolve().parent / "VERSION"

# Distribution name of the engine. It is the name `importlib.metadata` knows,
# NOT the import package name, which is `tree_engine`.
TREE_ENGINE_DISTRIBUTION: str = "ai-editor-tree-engine"

# Distribution name of this server, as published and as reported by `health`.
SERVER_DISTRIBUTION: str = "ai-editor"


class VersionDeclarationError(RuntimeError):
    """This build carries no readable version declaration.

    Raised at import of this module. There is no fallback value on purpose: a
    guessed version would let a mismatched engine or client through, which is
    the exact outcome the declaration exists to prevent.
    """


def _read_declared_version() -> str:
    """Return the one number this build declares, or refuse to load."""
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionDeclarationError(
            f"the ai-editor version declaration is unreadable at {VERSION_FILE}: "
            f"{exc.__class__.__name__}: {exc}. This file is package data copied "
            "from the repository-root VERSION file; a build without it cannot "
            "state which version it is and must not run."
        ) from exc
    declared = raw.strip()
    if not declared:
        raise VersionDeclarationError(
            f"the ai-editor version declaration at {VERSION_FILE} is empty; it "
            "must hold exactly one release number, e.g. '1.0.93'."
        )
    return declared


#: The version THIS build of the ai-editor server is.
DECLARED_VERSION: str = _read_declared_version()

#: The version of ``ai-editor-tree-engine`` this build REQUIRES, exactly.
#:
#: Equality is exact, never a compatible range. The engine owns node identity
#: and the on-disk tree file format, so running the server against a different
#: engine risks writing a tree file this server cannot read back -- data
#: corruption, not a degraded feature. `ai_editor.core.dependency_compat`
#: enforces this at startup; `pyproject.toml` pins the same number at packaging
#: time; `tests/unit/test_version_pinning.py` keeps the two in step.
REQUIRED_TREE_ENGINE_VERSION: str = DECLARED_VERSION

#: The version of ``ai-editor-client`` this build requires, exactly. The client
#: enforces this from its own side (it cannot import this package -- it is a
#: separate distribution), reading the same number from its own copy of the
#: shared VERSION file. See `ai_editor_client.server_version`.
REQUIRED_CLIENT_VERSION: str = DECLARED_VERSION

__all__ = [
    "DECLARED_VERSION",
    "REQUIRED_CLIENT_VERSION",
    "REQUIRED_TREE_ENGINE_VERSION",
    "SERVER_DISTRIBUTION",
    "TREE_ENGINE_DISTRIBUTION",
    "VERSION_FILE",
    "VersionDeclarationError",
]
