"""
Shared substantial test file content for fixtures.

Provides multi-line docstrings and real code phrases so that fulltext
and semantic search can find meaningful results (validation, configuration,
process data, etc.) instead of minimal "two words in three lines" content.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Default test file content: module + TestClass + test_method + test_function
DEFAULT_TEST_FILE_CONTENT = '''"""
Test module for code analysis and search validation.

This module provides sample classes and functions used by integration tests
to verify fulltext search (FTS5), semantic search, and code mapper indexing.
"""


class TestClass:
    """Helper class for validation and configuration in tests."""

    def test_method(self):
        """Validates input configuration and returns True if settings are correct.

        Used by the pipeline to ensure required options are present.
        """
        return True


def test_function():
    """Processes raw data and returns normalized result.

    Supports batch validation and is used by search integration tests.
    """
    return None
'''

# Same as default but test_function has return type and updated docstring (for compose tests)
UPDATED_TEST_FUNCTION_CONTENT = '''"""
Test module for code analysis and search validation.

This module provides sample classes and functions used by integration tests
to verify fulltext search (FTS5), semantic search, and code mapper indexing.
"""


class TestClass:
    """Helper class for validation and configuration in tests."""

    def test_method(self):
        """Validates input configuration and returns True if settings are correct.

        Used by the pipeline to ensure required options are present.
        """
        return True


def test_function() -> str:
    """Updated test function with explicit return type.

    Returns:
        Updated string used by CST-related integration tests.
    """
    return "updated"
'''

# Content for tests that need ClassA / ClassB and function_a / function_b
FILE_CONTENT_CLASS_A_B = '''"""
Test module with two classes and two functions for file splitter tests.

Contains validation logic and configuration helpers used by
integration tests for refactoring and code mapper.
"""


class ClassA:
    """First sample class: holds validation and configuration helpers."""

    def method_a(self):
        """Validates configuration and returns whether the setup is correct."""
        return True


class ClassB:
    """Second sample class: processes data and normalizes output."""

    def method_b(self):
        """Processes raw input and returns normalized result for the pipeline."""
        return None


def function_a():
    """Standalone validation helper used by search and analysis tests."""
    return True


def function_b():
    """Standalone processor for batch validation in integration tests."""
    return None
'''

# Content for tests that need MyClass with __init__ and get_value (ast/cst chunks)
FILE_CONTENT_MYCLASS = '''"""
Test file with MyClass and standalone function for AST/CST chunk verification.

Provides sample entities with multi-line docstrings so that code_content
and code_content_fts indexes contain searchable phrases.
"""


class MyClass:
    """Sample class with constructor and getter for chunk verification."""

    def __init__(self, value: int):
        """Initialize instance with the given integer value."""
        self.value = value

    def get_value(self) -> int:
        """Return the stored value. Used by verification tests."""
        return self.value


def standalone_function(param: str) -> str:
    """Convert input string to uppercase. Used by fulltext search tests."""
    return param.upper()
'''
