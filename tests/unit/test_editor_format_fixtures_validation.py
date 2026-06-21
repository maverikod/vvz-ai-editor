"""Ensure editor_format_test fixture files pass pre-write validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
)
from ai_editor.core.file_validation.pre_write_pipeline import validate_before_promote

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "editor_format_test" / "test_run"

_HANDLER_BY_SUFFIX = {
    ".py": HANDLER_PYTHON,
    ".json": HANDLER_JSON,
    ".md": HANDLER_TEXT,
}


@pytest.mark.parametrize(
    "fixture_path",
    sorted(
        p
        for p in _FIXTURE_ROOT.iterdir()
        if p.is_file() and p.suffix in _HANDLER_BY_SUFFIX
    ),
    ids=lambda p: p.name,
)
def test_editor_format_fixture_passes_pre_write_validation(fixture_path: Path) -> None:
    handler_id = _HANDLER_BY_SUFFIX[fixture_path.suffix]
    source = fixture_path.read_text(encoding="utf-8")
    target = fixture_path.with_suffix(f"{fixture_path.suffix}.target")
    outcome = validate_before_promote(
        handler_id,
        source_code=source,
        target_path=target,
        skip_quality_tools=handler_id != HANDLER_PYTHON,
    )
    assert outcome.success is True, outcome.error_message
    if outcome.temp_path is not None:
        outcome.temp_path.unlink(missing_ok=True)
