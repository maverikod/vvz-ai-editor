"""THE VERSION DECLARATION of this build of the ai-editor client.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

The owner's ruling is that the server (``ai-editor``), the client
(``ai-editor-client``) and the engine (``ai-editor-tree-engine``) always carry
the SAME version, enforced by the CODE and not only by tests: "if the server
and client versions differ -- an error. There must be a declaration."

This module is that declaration for the client distribution, and it is the only
place in ``ai_editor_client`` that decides what version this build is or what it
requires of a server. ``ai_editor_client.__version__`` is re-exported from here.

Why the client cannot simply import the server's declaration
------------------------------------------------------------

``ai-editor-client`` is a separate distribution, installed on its own from PyPI
with no ``ai_editor`` package anywhere on the machine. So there are two
declaration modules -- this one and ``ai_editor/version.py`` -- but only ONE
number: both read the same repository-root ``VERSION`` file, each through a
symlink of its own (``client/ai_editor_client/version.txt`` here), because
setuptools refuses to read a version file outside a distribution's own root
(``setuptools.config.expand._assert_local``). sdist and wheel builds copy the
resolved content, so an installed wheel carries a real file here.

The exemption, and why it is not a loophole
-------------------------------------------

``health`` and ``info`` are exempt from the check and keep working against a
server of any version. That is operational, not a concession: they are exactly
the commands an operator reaches for to SEE that the versions differ. Refusing
them would take away the instrument needed to diagnose the very failure this
module reports. Nothing else is exempt, and ``health`` is also how the server's
version is learned in the first place.

Failure policy
--------------

The check fails CLOSED. A server that does not answer ``health``, or answers
without a usable ``version``, is a server whose version could not be
established -- that raises :class:`ServerVersionMismatch` just as a wrong
number does. There is no "assume it is fine" path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from ai_editor_client.exceptions import ServerVersionMismatch

# The declaration file, shipped as package data (see `[tool.setuptools.
# package-data]` in client/pyproject.toml). In the repository it is a symlink to
# the root VERSION file; in an installed wheel it is that file's content.
VERSION_FILE: Path = Path(__file__).resolve().parent / "version.txt"

#: The command whose response carries the server's version.
SERVER_VERSION_PROBE_COMMAND: str = "health"

#: Commands that must keep working across a version mismatch, because they are
#: the ones used to diagnose it. Deliberately minimal.
VERSION_EXEMPT_COMMANDS: frozenset[str] = frozenset({"health", "info"})


class VersionDeclarationError(RuntimeError):
    """This build carries no readable version declaration.

    Raised at import. There is no fallback number on purpose: a guessed client
    version would silently "match" or silently mismatch every server.
    """


def _read_declared_version() -> str:
    """Return the one number this build declares, or refuse to load."""
    try:
        raw = VERSION_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise VersionDeclarationError(
            f"the ai-editor-client version declaration is unreadable at "
            f"{VERSION_FILE}: {exc.__class__.__name__}: {exc}. This file is "
            "package data copied from the repository-root VERSION file; a build "
            "without it cannot state which version it is and must not run."
        ) from exc
    declared = raw.strip()
    if not declared:
        raise VersionDeclarationError(
            f"the ai-editor-client version declaration at {VERSION_FILE} is "
            "empty; it must hold exactly one release number, e.g. '1.0.93'."
        )
    return declared


#: The version THIS build of the client is.
DECLARED_VERSION: str = _read_declared_version()

#: The version of the ai-editor server this build talks to, exactly. Equality
#: is exact, never a compatible range.
REQUIRED_SERVER_VERSION: str = DECLARED_VERSION


def is_version_exempt(command: str) -> bool:
    """True for the commands that must survive a version mismatch."""
    return command in VERSION_EXEMPT_COMMANDS


def server_version_from_health(envelope: Any) -> Optional[str]:
    """Pull the server version out of a ``health`` response envelope.

    ``None`` means the envelope did not carry a usable version -- an error
    result, an unexpected shape, or a non-string value. The caller treats that
    as an unverified server, not as a pass.
    """
    if not isinstance(envelope, Mapping):
        return None
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        return None
    version = data.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def assert_server_version_matches(
    server_version: Optional[str],
    *,
    command: Optional[str] = None,
) -> None:
    """Raise :class:`ServerVersionMismatch` unless the server is the declared one."""
    if server_version == REQUIRED_SERVER_VERSION:
        return
    where = f" while dispatching {command!r}" if command else ""
    if server_version is None:
        detail = (
            "the server did not report a usable version"
            f" -- {SERVER_VERSION_PROBE_COMMAND!r} returned no string "
            "'version' field, so which build is answering could not be "
            "established. A server whose version is unknown is not a server "
            "this client may send work to."
        )
    else:
        detail = (
            f"the server is version {server_version}. The versions must be "
            "EQUAL, not merely compatible. Install ai-editor-client=="
            f"{server_version} to talk to this server, or deploy an ai-editor "
            f"server of version {REQUIRED_SERVER_VERSION}."
        )
    raise ServerVersionMismatch(
        f"ai-editor-client {REQUIRED_SERVER_VERSION} refuses to continue"
        f"{where}: {detail} The requirement is declared in {VERSION_FILE} and "
        "read by ai_editor_client/server_version.py as REQUIRED_SERVER_VERSION. "
        f"The commands {sorted(VERSION_EXEMPT_COMMANDS)} stay available across a "
        "mismatch so the problem can be inspected.",
        client_version=REQUIRED_SERVER_VERSION,
        server_version=server_version,
        command=command,
    )


__all__ = [
    "DECLARED_VERSION",
    "REQUIRED_SERVER_VERSION",
    "SERVER_VERSION_PROBE_COMMAND",
    "VERSION_EXEMPT_COMMANDS",
    "VERSION_FILE",
    "VersionDeclarationError",
    "assert_server_version_matches",
    "is_version_exempt",
    "server_version_from_health",
]
