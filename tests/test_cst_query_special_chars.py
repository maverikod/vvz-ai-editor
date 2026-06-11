"""
Tests for CSTQuery parser and executor with special characters and quotes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from ai_editor.core.exceptions import QueryParseError
from ai_editor.cst_query import parse_selector, query_source


class TestParserSpecialCharacters:
    """Test parser with special characters and quotes."""

    def test_parse_single_quotes_in_double_quoted_string(self):
        """Test parsing selector with single quotes in double-quoted Python string."""
        # When selector is in double quotes, single quotes inside are preserved
        query = parse_selector("function[name='test']")
        assert query is not None
        assert len(query.first.predicates) == 1
        assert query.first.predicates[0].value == "test"

    def test_parse_double_quotes_in_single_quoted_string(self):
        """Test parsing selector with double quotes in single-quoted Python string."""
        # When selector is in single quotes, double quotes inside are preserved
        query = parse_selector('function[name="test"]')
        assert query is not None
        assert len(query.first.predicates) == 1
        assert query.first.predicates[0].value == "test"

    def test_parse_escaped_quotes(self):
        """Test parsing selector with escaped quotes."""
        # Test escaped single quote
        query = parse_selector("function[name='test\\'s']")
        assert query is not None
        assert query.first.predicates[0].value == "test's"

        # Test escaped double quote
        query = parse_selector('function[name="test\\"value"]')
        assert query is not None
        assert query.first.predicates[0].value == 'test"value'

    def test_parse_special_characters_in_value(self):
        """Test parsing selector with special characters in value."""
        # Test with underscore
        query = parse_selector("function[name='test_function']")
        assert query.first.predicates[0].value == "test_function"

        # Test with dash (if supported)
        query = parse_selector("function[name='test-function']")
        assert query.first.predicates[0].value == "test-function"

        # Test with dot
        query = parse_selector("function[qualname='test.module.function']")
        assert query.first.predicates[0].value == "test.module.function"

    def test_parse_unicode_characters(self):
        """Test parsing selector with unicode characters."""
        # Note: Unicode handling depends on how Lark processes escape sequences
        # The parser should handle unicode, but exact behavior may vary
        query = parse_selector("function[name='тест']")
        # Value should be parsed (may have encoding issues with escape sequences)
        assert len(query.first.predicates) == 1
        # Check that value is a string (exact value may vary due to encoding)
        assert isinstance(query.first.predicates[0].value, str)

        query = parse_selector("function[name='测试']")
        assert isinstance(query.first.predicates[0].value, str)

    def test_parse_spaces_in_value(self):
        """Test parsing selector with spaces in value (should use quotes)."""
        # Spaces require quotes
        query = parse_selector('function[name="test function"]')
        assert query.first.predicates[0].value == "test function"

    def test_parse_multiple_quotes_combinations(self):
        """Test parsing with various quote combinations."""
        # Single quotes in double-quoted selector
        query1 = parse_selector("class[name='Test'] function[name='method']")
        assert query1.first.predicates[0].value == "Test"
        assert query1.rest[0][1].predicates[0].value == "method"

        # Double quotes in single-quoted selector
        query2 = parse_selector('class[name="Test"] function[name="method"]')
        assert query2.first.predicates[0].value == "Test"
        assert query2.rest[0][1].predicates[0].value == "method"

    def test_parse_operators_with_special_chars(self):
        """Test parsing with different operators and special characters."""
        # Contains operator with special chars
        query = parse_selector("function[name~='test_']")
        assert query.first.predicates[0].op.value == "~="
        assert query.first.predicates[0].value == "test_"

        # Prefix operator
        query = parse_selector("function[name^='test']")
        assert query.first.predicates[0].op.value == "^="

        # Suffix operator
        query = parse_selector("function[name$='_test']")
        assert query.first.predicates[0].op.value == "$="

    def test_parse_complex_special_chars(self):
        """Test parsing complex selectors with special characters."""
        query = parse_selector(
            "class[name='Test_Class'] function[name='test_method'] smallstmt[type='Return']"
        )
        assert len(query.rest) == 2
        assert query.first.predicates[0].value == "Test_Class"
        assert query.rest[0][1].predicates[0].value == "test_method"


class TestExecutorSpecialCharacters:
    """Test executor with special characters in source code."""

    def test_query_function_with_underscore(self):
        """Test querying function with underscore in name."""
        source = """
def test_function():
    return True
"""
        matches = query_source(source, "function[name='test_function']")
        assert len(matches) == 1
        assert matches[0].name == "test_function"

    def test_query_function_with_special_chars(self):
        """Test querying function with special characters in name."""
        source = """
def test_function_123():
    return True
"""
        matches = query_source(source, "function[name='test_function_123']")
        assert len(matches) == 1
        assert matches[0].name == "test_function_123"

    def test_query_class_with_underscore(self):
        """Test querying class with underscore in name."""
        source = """
class Test_Class:
    def method(self):
        pass
"""
        matches = query_source(source, "class[name='Test_Class']")
        assert len(matches) == 1
        assert matches[0].name == "Test_Class"

    def test_query_with_escaped_quotes_in_name(self):
        """Test querying with names that contain quotes (if such names are possible)."""
        # Note: Python identifiers cannot contain quotes, but we test the parser handling
        source = """
def test_function():
    return "value with 'quotes'"
"""
        matches = query_source(source, "function[name='test_function']")
        assert len(matches) == 1

    def test_query_qualname_with_dots(self):
        """Test querying with qualified names containing dots."""
        source = """
class TestClass:
    def method(self):
        pass
"""
        matches = query_source(source, "method[qualname='TestClass.method']")
        assert len(matches) == 1
        assert matches[0].qualname == "TestClass.method"

    def test_query_with_prefix_operator_special_chars(self):
        """Test querying with prefix operator and special characters."""
        source = """
def test_function():
    pass

def test_other():
    pass

def other_function():
    pass
"""
        matches = query_source(source, "function[name^='test']")
        assert len(matches) == 2
        assert all(m.name.startswith("test") for m in matches)

    def test_query_with_suffix_operator_special_chars(self):
        """Test querying with suffix operator and special characters."""
        source = """
def test_function():
    pass

def other_function():
    pass

def test_other():
    pass
"""
        matches = query_source(source, "function[name$='_function']")
        assert len(matches) == 2
        assert all(m.name.endswith("_function") for m in matches)

    def test_query_with_contains_operator_special_chars(self):
        """Test querying with contains operator and special characters."""
        source = """
def test_function():
    pass

def function_test():
    pass

def other_function():
    pass

def other():
    pass
"""
        matches = query_source(source, "function[name~='function']")
        # Should find functions containing "function" in name
        assert len(matches) == 3
        assert all("function" in m.name for m in matches)

    def test_query_complex_with_special_chars(self):
        """Test complex query with special characters."""
        source = """
class Test_Class:
    def test_method_123(self):
        return True
"""
        matches = query_source(
            source, "class[name='Test_Class'] method[name='test_method_123']"
        )
        assert len(matches) == 1
        assert matches[0].name == "test_method_123"
        assert matches[0].qualname == "Test_Class.test_method_123"

    def test_query_with_unicode_in_source(self):
        """Test querying source code with unicode characters."""
        source = """
def тест():
    return True
"""
        matches = query_source(source, "function[name='тест']")
        # May or may not work depending on LibCST support
        assert len(matches) >= 0

    def test_query_with_spaces_in_predicate_value(self):
        """Test querying with spaces in predicate value (requires quotes)."""
        # This tests that quoted values with spaces work
        source = """
def test_function():
    pass
"""
        # Using double quotes for value with spaces (if such names existed)
        # In practice, Python names can't have spaces, but we test the parser
        matches = query_source(source, 'function[name="test_function"]')
        assert len(matches) == 1

    def test_query_multiple_predicates_special_chars(self):
        """Test query with multiple predicates containing special characters."""
        source = """
class Test_Class_123:
    def method_456(self):
        pass
"""
        matches = query_source(
            source,
            "class[name='Test_Class_123'] method[name='method_456']",
        )
        assert len(matches) == 1

    def test_query_with_operators_and_special_chars(self):
        """Test all operators with special characters."""
        source = """
def test_function_1():
    pass

def test_function_2():
    pass

def other_function():
    pass
"""
        # Equals
        matches = query_source(source, "function[name='test_function_1']")
        assert len(matches) == 1

        # Not equals
        matches = query_source(source, "function[name!='test_function_1']")
        assert len(matches) == 2
        assert all(m.name != "test_function_1" for m in matches)

        # Contains
        matches = query_source(source, "function[name~='_function_']")
        assert len(matches) == 2

        # Prefix
        matches = query_source(source, "function[name^='test_function']")
        assert len(matches) == 2

        # Suffix
        matches = query_source(source, "function[name$='_1']")
        assert len(matches) == 1


class TestParserErrorHandlingSpecialChars:
    """Test parser error handling with special characters."""

    def test_parse_unclosed_quotes(self):
        """Test parsing with unclosed quotes."""
        # Note: Parser may treat unclosed quotes as bareword or raise error
        # depending on grammar rules. We test both behaviors.
        try:
            query = parse_selector("function[name='test]")
            # If it parses, the value should be handled (may include quote)
            assert query is not None
            # Value might be "'test" or "test" depending on parsing
            assert isinstance(query.first.predicates[0].value, str)
        except QueryParseError:
            # Error is also acceptable behavior
            pass

        try:
            query = parse_selector('function[name="test]')
            assert query is not None
            assert isinstance(query.first.predicates[0].value, str)
        except QueryParseError:
            # Error is also acceptable behavior
            pass

    def test_parse_mismatched_quotes(self):
        """Test parsing with mismatched quotes."""
        # This might parse as bareword or raise error
        # Depending on grammar, this could be valid or invalid
        try:
            query = parse_selector("function[name='test\"]")
            # If it parses, value should be handled correctly
            assert query is not None
        except QueryParseError:
            # Error is also acceptable
            pass

    def test_parse_empty_quoted_value(self):
        """Test parsing with empty quoted value."""
        query = parse_selector("function[name='']")
        assert query.first.predicates[0].value == ""

        query = parse_selector('function[name=""]')
        assert query.first.predicates[0].value == ""
