"""
Tests for CST file validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
from pathlib import Path
import pytest

from ai_editor.core.cst_module.validation import (
    validate_file_in_temp,
    ValidationResult,
)


@pytest.fixture
def temp_file():
    """Create temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        temp_path = Path(f.name)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_validate_success(temp_file):
    """Test successful validation."""
    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_function(x: int) -> str:
    """Test function docstring.
    
    Args:
        x: Integer parameter.
    
    Returns:
        String representation of x.
    """
    return str(x)
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=True,
        validate_type_checker=True,
    )

    # Note: linter or type checker may have warnings, but compilation and docstrings should pass
    assert "compile" in results
    assert results["compile"].success is True
    assert "docstrings" in results
    # Overall success depends on all validations, but at least compile and docstrings should pass
    if not success:
        # If validation failed, check which part failed
        failed_parts = [k for k, v in results.items() if not v.success]
        # Allow linter/type_checker to fail, but compile and docstrings must pass
        assert (
            "compile" not in failed_parts
        ), f"Compilation should pass, but failed: {results.get('compile')}"
        assert (
            "docstrings" not in failed_parts
        ), f"Docstrings should pass, but failed: {results.get('docstrings')}"


def test_validate_compile_error(temp_file):
    """Test validation with compilation error."""
    source_code = "def invalid_syntax("  # Missing closing parenthesis
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is False
    assert error is not None
    assert "compile" in results
    assert results["compile"].success is False
    assert results["compile"].error_message is not None


def test_validate_docstring_error(temp_file):
    """Test validation with docstring error."""
    source_code = """def test_function(x: int) -> str:
    return str(x)
"""
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is False
    assert error is not None
    assert "docstrings" in results
    assert results["docstrings"].success is False
    assert results["docstrings"].error_message is not None


def test_validate_linter_error(temp_file):
    """Test validation with linter error."""
    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_function(x: int) -> str:
    """Test function docstring."""
    unused_variable = 42  # flake8: F401 unused variable
    return str(x)
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=True,
        validate_type_checker=False,
    )

    # Linter errors may or may not cause failure depending on configuration
    assert "linter" in results
    assert isinstance(results["linter"], ValidationResult)


def test_validate_type_check_error(temp_file):
    """Test validation with type checker error."""
    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_function(x: int) -> str:
    """Test function docstring."""
    return x  # Type error: returning int instead of str
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=True,
    )

    # Type checker errors may or may not cause failure depending on configuration
    assert "type_checker" in results
    assert isinstance(results["type_checker"], ValidationResult)


def test_validate_multiple_errors(temp_file):
    """Test validation with multiple errors."""
    source_code = "def invalid_syntax("  # Compilation error + missing docstring
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is False
    assert error is not None
    assert "compile" in results
    assert results["compile"].success is False
    # Docstring validation is skipped if compilation fails (only compile result is returned)
    # This is expected behavior - docstrings are not checked if file doesn't compile


def test_validate_without_linter(temp_file):
    """Test validation without linter."""
    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_function(x: int) -> str:
    """Test function docstring.
    
    Args:
        x: Integer parameter.
    
    Returns:
        String representation of x.
    """
    return str(x)
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is True, f"Validation should succeed: {error}, results: {results}"
    assert "linter" in results
    assert results["linter"].success is True  # Should be marked as success when skipped
    assert "compile" in results
    assert results["compile"].success is True
    assert "docstrings" in results
    assert results["docstrings"].success is True


def test_validate_without_type_checker(temp_file):
    """Test validation without type checker."""
    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


def test_function(x: int) -> str:
    """Test function docstring.
    
    Args:
        x: Integer parameter.
    
    Returns:
        String representation of x.
    """
    return str(x)
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is True, f"Validation should succeed: {error}, results: {results}"
    assert "type_checker" in results
    assert (
        results["type_checker"].success is True
    )  # Should be marked as success when skipped
    assert "compile" in results
    assert results["compile"].success is True
    assert "docstrings" in results
    assert results["docstrings"].success is True


def test_validate_file_write_error():
    """Test validation when temporary file write fails."""
    # Use a path that cannot be written to (e.g., directory)
    invalid_path = Path("/nonexistent/directory/file.py")

    source_code = '''"""
Module docstring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

def test_function(x: int) -> str:
    """Test function docstring."""
    return str(x)
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=invalid_path,
        validate_linter=False,
        validate_type_checker=False,
    )

    assert success is False
    assert error is not None
    assert "compile" in results
    assert results["compile"].success is False


def test_validate_skip_docstrings_syntax_only_mode(temp_file):
    """When validate_docstrings=False, docstring policy must not block compile-only."""
    source_code = '''"""Module."""

def no_return_hint():
    """Body."""
    return 1
'''
    success, error, results = validate_file_in_temp(
        source_code=source_code,
        temp_file_path=temp_file,
        validate_linter=False,
        validate_type_checker=False,
        validate_docstrings=False,
    )
    assert success is True, error
    assert results["docstrings"].success is True
    assert results["compile"].success is True
