"""
Configuration validation wrapper: mcp-proxy-adapter SimpleConfigValidator first,
then AI Editor extension sections.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mcp_proxy_adapter.core.config.simple_config_validator import SimpleConfigValidator

from ai_editor.core.config_placeholders import (
    load_simple_config_model,
    resolve_config_placeholders,
)
from ai_editor.core.editor_config_extension import (
    EditorConfigValidationIssue,
    EditorExtensionValidator,
    adapter_validation_errors_to_issues,
)
from ai_editor.core.env_loader import load_dotenv_near_config


def collect_config_validation_issues(
    config_path: Path,
) -> Tuple[List[EditorConfigValidationIssue], Dict[str, Any]]:
    """
    Run adapter validator then editor-extension validator.

    Returns:
        (issues, resolved_config_dict). Empty dict when JSON parse fails.
        Placeholders ``${ENV}`` are resolved from the environment before validation.
    """
    config_file = config_path.resolve()
    load_dotenv_near_config(config_file)

    try:
        raw: Dict[str, Any] = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            [
                EditorConfigValidationIssue(
                    level="error",
                    message=f"Invalid JSON in configuration file: {exc}",
                )
            ],
            {},
        )
    except OSError as exc:
        return (
            [
                EditorConfigValidationIssue(
                    level="error",
                    message=f"Failed to read configuration file: {exc}",
                )
            ],
            {},
        )

    issues: List[EditorConfigValidationIssue] = []

    resolved_config, unresolved = resolve_config_placeholders(raw)
    for item in unresolved:
        issues.append(
            EditorConfigValidationIssue(
                level="error",
                message=(
                    f"Unresolved config placeholder {item.token}; set environment "
                    f"variable {item.name} in .env or the process environment"
                ),
                suggestion=(
                    f"Export {item.name}=... or copy .env.example to .env near the "
                    f"config file"
                ),
            )
        )
    if unresolved:
        return issues, raw

    try:
        model = load_simple_config_model(config_file, resolved_config)
    except Exception as exc:
        issues.append(
            EditorConfigValidationIssue(
                level="error",
                message=f"Adapter configuration parse error: {exc}",
                suggestion=(
                    "Fix server/client/registration sections or regenerate with "
                    "aiedcfg generate"
                ),
            )
        )
        return issues, raw

    adapter_errors = SimpleConfigValidator(str(config_file)).validate(model)
    issues.extend(adapter_validation_errors_to_issues(adapter_errors))
    issues.extend(EditorExtensionValidator(str(config_file)).validate(resolved_config))

    return issues, resolved_config


def assert_config_valid(config_path: Path) -> Dict[str, Any]:
    """
    Validate configuration; exit the process with code 1 on adapter/editor errors.

    Returns:
        Resolved configuration dict (placeholders substituted) when valid.
    """
    issues, resolved_config = collect_config_validation_issues(config_path)
    errors = [issue for issue in issues if issue.level == "error"]
    if errors:
        from ai_editor.main_validation import report_validation_failure

        summary = {
            "errors": len(errors),
            "warnings": sum(1 for issue in issues if issue.level == "warning"),
        }
        report_validation_failure(
            _issues_for_report(issues),
            summary,
            resolved_config or {},
            config_path.resolve(),
        )
    return resolved_config


def validate_config_file(config_path: Path) -> int:
    """
    CLI-oriented validation: print issues and return exit code.

    Returns:
        0 when valid, 1 when errors exist.
    """
    issues, _resolved = collect_config_validation_issues(config_path)
    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]

    if errors:
        print("Configuration is invalid:", file=sys.stderr)
        for issue in errors:
            line = f"  - {issue.message}"
            if issue.section:
                line += f" ({issue.section}"
                if issue.key:
                    line += f".{issue.key}"
                line += ")"
            if issue.suggestion:
                line += f" — {issue.suggestion}"
            print(line, file=sys.stderr)
        return 1

    if warnings:
        print("Warnings:", file=sys.stderr)
        for issue in warnings:
            print(f"  - {issue.message}", file=sys.stderr)

    print(f"Configuration is valid: {config_path.resolve()}")
    return 0


def _issues_for_report(
    issues: List[EditorConfigValidationIssue],
) -> List[Any]:
    """Adapt editor issues to main_validation.report_validation_failure shape."""

    class _ReportRow:
        def __init__(self, issue: EditorConfigValidationIssue) -> None:
            self.level = issue.level
            self.message = issue.message
            self.section = issue.section
            self.key = issue.key
            self.suggestion = issue.suggestion

    return [_ReportRow(issue) for issue in issues]
