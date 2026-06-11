"""
Main entry point for AI Editor server using mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import argparse
import logging
import os
import sys

from mcp_proxy_adapter.core.server_engine import ServerEngineFactory

from ai_editor.core.constants import DEFAULT_CONFIG_FILENAME
from ai_editor.core.settings_manager import get_settings
from ai_editor.main_app_factory import create_app_with_events, setup_main_logger_file_handler
from ai_editor.main_cleanup import log_daemon_shutdown, register_cleanup_handlers
from ai_editor.main_config import (
    apply_global_config,
    ensure_storage_and_load_app_config,
    load_config_and_validate,
)
from ai_editor.main_daemon_logging import setup_daemon_logging
from ai_editor.main_server_config import build_server_config
from ai_editor.main_startup_info import print_startup_info
from ai_editor.main_queue_init import init_queue_manager_before_workers
from ai_editor.core.dependency_compat import assert_queue_dependencies_compatible

from ai_editor import hooks  # noqa: F401


def main() -> None:
    """Main function to run AI Editor server."""
    parser = argparse.ArgumentParser(description="AI Editor Server")
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG_FILENAME,
        help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILENAME})",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Start the server (daemon mode). Without this flag the command prints startup info and exits.",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run server in foreground (no daemon). Use for debugging; faulthandler dumps to stderr on crash.",
    )
    parser.add_argument("--host", help="Server host (overrides config)")
    parser.add_argument("--port", type=int, help="Server port (overrides config)")
    args = parser.parse_args()

    settings = get_settings()
    cli_overrides = {}
    if args.host:
        cli_overrides["server_host"] = args.host
    if args.port:
        cli_overrides["server_port"] = args.port
    if cli_overrides:
        settings.set_cli_overrides(cli_overrides)

    import signal

    logging.raiseExceptions = False
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except Exception:
        pass

    config_path, full_config = load_config_and_validate(args)

    heartbeat_stop = setup_daemon_logging(args, full_config, config_path)

    app_config, simple_config, server_host, server_port = (
        ensure_storage_and_load_app_config(config_path, full_config, args)
    )
    queue_enabled = bool(
        (full_config.get("queue_manager") or {}).get("enabled", True)
        if isinstance(full_config, dict)
        else True
    )
    assert_queue_dependencies_compatible(queue_enabled=queue_enabled)
    apply_global_config(config_path, simple_config, app_config)

    init_queue_manager_before_workers(full_config)

    app = create_app_with_events(app_config, config_path)
    main_logger = setup_main_logger_file_handler(app_config)

    server_config = build_server_config(server_host, server_port, app_config)

    if not args.daemon and not args.foreground:
        print_startup_info(
            config_path=config_path,
            server_host=server_host,
            server_port=server_port,
            server_config=server_config,
            app_config=app_config,
        )
        return

    if args.foreground:
        try:
            import faulthandler

            faulthandler.enable()
        except Exception:
            pass

    register_cleanup_handlers(
        None,
        app_config,
        main_logger,
        heartbeat_stop=heartbeat_stop,
    )

    engine = ServerEngineFactory.get_engine("hypercorn")
    if not engine:
        print("❌ Hypercorn engine not available", file=sys.stderr)
        sys.exit(1)

    main_logger.info(
        "Starting Hypercorn server on %s:%s (pid=%s)",
        server_host,
        server_port,
        os.getpid(),
    )
    try:
        engine.run_server(app, server_config)
        main_logger.info("Hypercorn run_server returned (server loop ended normally)")
    except Exception as e:
        main_logger.error(
            "Hypercorn run_server raised: %s",
            e,
            exc_info=True,
        )
        raise
    finally:
        log_daemon_shutdown(main_logger, "main_server_loop_ended")
        main_logger.info("main() exiting after server loop")


if __name__ == "__main__":
    main()
