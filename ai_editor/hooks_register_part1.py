"""
Register minimal infrastructure commands for AI Editor (health only).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging

from mcp_proxy_adapter.commands.command_registry import registry

logger = logging.getLogger(__name__)


def register_commands_part1(reg: registry) -> None:
    """Register health commands."""
    try:
        from .commands.health_command import HealthCommand

        reg.register(HealthCommand, "custom")
    except ImportError:
        pass
