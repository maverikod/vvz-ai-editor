"""
Initialize the global queue manager before worker subprocesses start.

Python 3.14 multiprocessing rejects spawning the queuemgr manager process while
the main module is still bootstrapping other child processes. Workers must start
only after ``init_global_queue_manager`` has completed (external queuemgr package;
this module only controls call order in ai-editor-server).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _queue_config(full_config: Dict[str, Any]) -> Dict[str, Any]:
    raw = full_config.get("queue_manager")
    return raw if isinstance(raw, dict) else {}


def init_queue_manager_before_workers(full_config: Dict[str, Any]) -> None:
    """
    Start the global queue manager synchronously when enabled in config.

    Safe to call multiple times; skips when already running or disabled.
    Lifespan startup in mcp-proxy-adapter reuses the existing instance.
    """
    queue_config = _queue_config(full_config)
    if not queue_config.get("enabled", True):
        logger.info("Queue manager disabled; skipping pre-worker initialization")
        return

    try:
        from mcp_proxy_adapter.integrations import queuemgr_integration

        existing = queuemgr_integration._global_queue_manager
        if existing is not None and existing.is_running():
            logger.info("Queue manager already running; skipping pre-worker init")
            return
    except Exception:
        pass

    from mcp_proxy_adapter.integrations.queuemgr_integration import (
        init_global_queue_manager,
    )

    async def _init() -> None:
        await init_global_queue_manager(
            registry_path=queue_config.get("registry_path"),
            shutdown_timeout=float(queue_config.get("shutdown_timeout", 30.0)),
            max_concurrent_jobs=int(queue_config.get("max_concurrent_jobs", 10)),
            in_memory=bool(queue_config.get("in_memory", True)),
            max_queue_size=queue_config.get("max_queue_size"),
            per_job_type_limits=queue_config.get("per_job_type_limits"),
            completed_job_retention_seconds=int(
                queue_config.get("completed_job_retention_seconds", 21600)
            ),
            command_timeout=queue_config.get("command_timeout"),
            stop_job_wait_timeout=queue_config.get("stop_job_wait_timeout"),
        )

    logger.info(
        "Initializing queue manager before worker subprocesses (in_memory=%s)",
        queue_config.get("in_memory", True),
    )
    try:
        multiprocessing.set_start_method("fork")
    except RuntimeError:
        pass

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            asyncio.run(_init())
            logger.info("Queue manager ready before worker subprocesses")
            return
        except Exception as exc:
            last_error = exc
            err = str(exc).lower()
            if "timed out" in err and attempt < 3:
                logger.warning(
                    "Queue manager init attempt %s/3 timed out; retrying in 2s",
                    attempt,
                )
                time.sleep(2.0)
                continue
            raise
    if last_error is not None:
        raise last_error
