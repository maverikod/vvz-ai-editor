"""
SecurityPolicy evaluator: is_command_permitted modes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_editor.core.security_policy import (
    POLICY_ALLOWLIST,
    POLICY_DENYLIST,
    POLICY_DISABLED,
    is_command_permitted,
)


def test_is_command_permitted_disabled_always_true_no_db() -> None:
    database = MagicMock()
    with patch("ai_editor.core.security_policy._get_roles_for_session") as get_roles:
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_list",
                "srv-uuid",
                POLICY_DISABLED,
            )
            is True
        )
        get_roles.assert_not_called()


def test_is_command_permitted_allowlist_requires_permission() -> None:
    database = MagicMock()
    with (
        patch(
            "ai_editor.core.security_policy._get_roles_for_session",
            return_value=[{"role_id": "r1", "name": "admin"}],
        ),
        patch(
            "ai_editor.core.security_policy._get_permissions_for_roles",
            return_value=["session_list", "session_create"],
        ) as get_perms,
    ):
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_list",
                "srv-uuid",
                POLICY_ALLOWLIST,
            )
            is True
        )
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_delete",
                "srv-uuid",
                POLICY_ALLOWLIST,
            )
            is False
        )
        get_perms.assert_called_with(database, ["r1"], "srv-uuid")


def test_is_command_permitted_allowlist_denies_without_roles() -> None:
    database = MagicMock()
    with patch(
        "ai_editor.core.security_policy._get_roles_for_session",
        return_value=[],
    ):
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_list",
                "srv-uuid",
                POLICY_ALLOWLIST,
            )
            is False
        )


def test_is_command_permitted_denylist_blocks_listed_command() -> None:
    database = MagicMock()
    with (
        patch(
            "ai_editor.core.security_policy._get_roles_for_session",
            return_value=[{"role_id": "r1", "name": "limited"}],
        ),
        patch(
            "ai_editor.core.security_policy._get_permissions_for_roles",
            return_value=["session_delete"],
        ),
    ):
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_delete",
                "srv-uuid",
                POLICY_DENYLIST,
            )
            is False
        )
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_list",
                "srv-uuid",
                POLICY_DENYLIST,
            )
            is True
        )


def test_is_command_permitted_denylist_permits_without_roles() -> None:
    database = MagicMock()
    with patch(
        "ai_editor.core.security_policy._get_roles_for_session",
        return_value=[],
    ):
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "any_command",
                "srv-uuid",
                POLICY_DENYLIST,
            )
            is True
        )


def test_is_command_permitted_unknown_mode_fails_closed() -> None:
    database = MagicMock()
    with patch(
        "ai_editor.core.security_policy._get_roles_for_session",
        return_value=[{"role_id": "r1", "name": "x"}],
    ):
        assert (
            is_command_permitted(
                database,
                "sess-1",
                "session_list",
                "srv-uuid",
                "strict",
            )
            is False
        )
