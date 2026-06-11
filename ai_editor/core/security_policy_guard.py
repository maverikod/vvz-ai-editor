"""
SecurityPolicy enforcement guard for MCP command boundaries.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any


class CommandForbiddenError(ValueError):
    """Raised when SecurityPolicy denies a command for a session."""

    def __init__(
        self,
        session_id: str,
        command_name: str,
        server_uuid: str,
        policy_mode: str,
    ) -> None:
        super().__init__(
            f"Command {command_name!r} is forbidden for session {session_id!r} "
            f"under policy {policy_mode!r} on server {server_uuid!r}."
        )
        self.session_id = session_id
        self.command_name = command_name
        self.server_uuid = server_uuid
        self.policy_mode = policy_mode


def enforce_security_policy(
    database: Any,
    session_id: str,
    command_name: str,
    server_uuid: str,
    policy_mode: str,
) -> None:
    """
    Enforce SecurityPolicy at the MCP command boundary.

    Calls is_command_permitted from security_policy module. Raises
    CommandForbiddenError if the command is not permitted under the given
    policy mode. Returns None (silently) if permitted.

    Execution order contract (C-003, C-005, C-009):
      1. SessionTouchRule (touch_or_error) — call before this function.
      2. enforce_security_policy (this function).
      3. Main command logic.

    Args:
        database: DB connection with .execute() method.
        session_id: UUID4 of the active session.
        command_name: MCP command name being executed.
        server_uuid: UUID4 of the proxy server.
        policy_mode: One of 'disabled', 'allowlist', 'denylist'.

    Raises:
        CommandForbiddenError: if is_command_permitted returns False.
    """
    from ai_editor.core.security_policy import is_command_permitted

    if not is_command_permitted(
        database=database,
        session_id=session_id,
        command_name=command_name,
        server_uuid=server_uuid,
        policy_mode=policy_mode,
    ):
        raise CommandForbiddenError(
            session_id=session_id,
            command_name=command_name,
            server_uuid=server_uuid,
            policy_mode=policy_mode,
        )
