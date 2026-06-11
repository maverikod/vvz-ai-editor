"""Tests for CST docstring validation (validate_module_docstrings)."""

from __future__ import annotations

import ast

from ai_editor.core.cst_module.docstring_validator import (
    _extract_class_attributes,
    validate_module_docstrings,
)


def test_extract_class_attributes_includes_init_and_property() -> None:
    src = '''
class Foo:
    """Doc."""

    limit: int = 1

    def __init__(self, name: str) -> None:
        self.name = name
        self.color: str = "red"

    @property
    def label(self) -> str:
        return self.name
'''
    cls = ast.parse(src).body[0]
    assert isinstance(cls, ast.ClassDef)
    attrs = _extract_class_attributes(cls)
    assert attrs == ["color", "label", "limit", "name"]


def test_validate_class_docstring_accepts_attributes_section() -> None:
    src = '''
"""Module."""

class Circle:
    """A circle.

    Attributes:
        label: Display label.
        diameter: Diameter in units.
    """

    def __init__(self, diameter: float) -> None:
        """Initialize circle.

        Args:
            diameter: Circle diameter.
        """
        self.diameter = diameter

    @property
    def label(self) -> str:
        """Display label.

        Returns:
            Label text.
        """
        return "circle"
'''
    ok, _msg, errors = validate_module_docstrings(src)
    assert ok, errors
    assert errors == []


def test_validate_class_method_not_validated_twice() -> None:
    """Class methods must not be re-validated as top-level via ast.walk."""
    src = '''
"""Module."""

class Shape:
    """A shape."""

    def label(self) -> str:
        pass
'''
    _ok, _msg, errors = validate_module_docstrings(src)
    missing_doc = [e for e in errors if "missing docstring" in e.lower()]
    assert len(missing_doc) == 1
    assert "Shape.label" in missing_doc[0]
    assert not any(e for e in missing_doc if "label" in e and "Shape.label" not in e)


def test_validate_class_docstring_reports_missing_init_attr() -> None:
    src = '''
"""Module."""

class Box:
  """A box."""

  def __init__(self, width: float) -> None:
      self.width = width
'''
    ok, _msg, errors = validate_module_docstrings(src)
    assert not ok
    assert any("width" in e for e in errors)
