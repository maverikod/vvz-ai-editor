"""
Tracked implementation deferrals for the marked-tree package.

G1-13-python-cst-integration: RESOLVED in marked_tree_unification plan.
PythonHandler uses cst_tree wrapper and integer ___id___ markers (HRS {b005}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

DeferralStatus = Literal["open", "resolved_in_plan", "superseded"]

TRACKED_DEFERRALS: Dict[str, Dict[str, Any]] = {
    "G1-13-python-cst-integration": {
        "deferral_id": "G1-13-python-cst-integration",
        "status": "resolved_in_plan",
        "reason": (
            "PythonHandler in ai_editor/tree/handlers/python_handler.py implements "
            "full CST integration via the cst_tree wrapper with integer short_id hybrid "
            "markers per HRS {b005}; supersedes G2-CORR-001."
        ),
        "owner_plan": "marked_tree_unification",
        "resolution_target": "ai_editor/tree/handlers/python_handler.py",
        "target": "ai_editor.tree.handlers.python_handler.PythonHandler",
        "methods": ["parse_content", "mark", "unmark", "sidecar_path"],
        "supersedes": ["G2-CORR-001"],
    },
}


def get_deferral(deferral_id: str) -> Optional[Dict[str, Any]]:
    """Return the tracked deferral record for *deferral_id*, or None if unknown."""
    return TRACKED_DEFERRALS.get(deferral_id)


def is_deferred(deferral_id: str) -> bool:
    """Return True only when the deferral exists and its status is ``open``."""
    record = TRACKED_DEFERRALS.get(deferral_id)
    if record is None:
        return False
    return bool(record["status"] == "open")


def is_resolved(deferral_id: str) -> bool:
    """Return True when the deferral exists and its status is ``resolved_in_plan``."""
    record = TRACKED_DEFERRALS.get(deferral_id)
    if record is None:
        return False
    return bool(record["status"] == "resolved_in_plan")
