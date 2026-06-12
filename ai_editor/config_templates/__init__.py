"""
Bundled configuration templates shipped with the ai-editor package.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

CONTAINER_TEMPLATE_NAME = "ai_editor_container.json"


def _templates_root():
    return resources.files(__name__)


def bundled_template_names() -> tuple[str, ...]:
    """Return names of JSON templates included in the package."""
    return (CONTAINER_TEMPLATE_NAME,)


def read_bundled_template_text(name: str = CONTAINER_TEMPLATE_NAME) -> str:
    """Read raw JSON text for a bundled template."""
    return _templates_root().joinpath(name).read_text(encoding="utf-8")


def load_bundled_template(name: str = CONTAINER_TEMPLATE_NAME) -> dict[str, Any]:
    """Load a bundled template as a dict."""
    data: Any = json.loads(read_bundled_template_text(name))
    if not isinstance(data, dict):
        raise ValueError(f"Template {name!r} must be a JSON object")
    return data


def copy_bundled_template(
    dest_dir: str | Path,
    *,
    name: str = CONTAINER_TEMPLATE_NAME,
    overwrite: bool = False,
) -> Path:
    """
    Copy a bundled template into *dest_dir*.

    Returns the destination file path. Skips write when the file exists and
    *overwrite* is False.
    """
    dest = Path(dest_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / name
    if out.exists() and not overwrite:
        return out
    out.write_text(read_bundled_template_text(name), encoding="utf-8")
    return out
