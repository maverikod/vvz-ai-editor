"""
Tests for CSTQuery parser.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from ai_editor.core.exceptions import QueryParseError
from ai_editor.cst_query import parse_selector
from ai_editor.cst_query.ast import Combinator

_HRS_J003_SELECTOR = "//ClassDef//FunctionDef[@name='execute'][start_line>=100]"


class TestParserBasic:
    """Test basic parser functionality."""

    def test_parse_simple_type(self):
        """Test parsing simple type selector."""
        query = parse_selector("function")
        assert query is not None
        assert query.first.node_type == "function"
        assert len(query.rest) == 0

    def test_parse_wildcard(self):
        """Test parsing wildcard selector."""
        query = parse_selector("*")
        assert query is not None
        assert query.first.node_type == "*"
        assert len(query.rest) == 0

    def test_parse_type_wildcard_modifier(self):
        """Test parsing type modifier Def:* (prefix/suffix match on node type)."""
        query = parse_selector("Def:*")
        assert query is not None
        assert query.first.node_type == "Def:*"
        query2 = parse_selector("FunctionDef:*")
        assert query2.first.node_type == "FunctionDef:*"

    def test_parse_with_predicate(self):
        """Test parsing selector with predicate."""
        query = parse_selector("function[name='test']")
        assert query is not None
        assert len(query.first.predicates) == 1
        assert query.first.predicates[0].attr == "name"
        assert query.first.predicates[0].op.value == "="
        # Parser should remove quotes from values
        assert query.first.predicates[0].value == "test"

    def test_parse_with_multiple_predicates(self):
        """Test parsing selector with multiple predicates."""
        query = parse_selector("class[name='Test'][qualname='test.Test']")
        assert query is not None
        assert len(query.first.predicates) == 2

    def test_parse_descendant_combinator(self):
        """Test parsing descendant combinator."""
        query = parse_selector("class function")
        assert query is not None
        assert len(query.rest) == 1
        assert query.rest[0][0].value == " "  # DESCENDANT

    def test_parse_child_combinator(self):
        """Test parsing child combinator."""
        query = parse_selector("class > function")
        assert query is not None
        assert len(query.rest) == 1
        assert query.rest[0][0].value == ">"  # CHILD

    def test_parse_with_pseudo_first(self):
        """Test parsing selector with :first pseudo."""
        query = parse_selector("function:first")
        assert query is not None
        assert len(query.first.pseudos) == 1
        assert query.first.pseudos[0].kind.value == "first"

    def test_parse_with_pseudo_last(self):
        """Test parsing selector with :last pseudo."""
        query = parse_selector("function:last")
        assert query is not None
        assert len(query.first.pseudos) == 1
        assert query.first.pseudos[0].kind.value == "last"

    def test_parse_with_pseudo_nth(self):
        """Test parsing selector with :nth pseudo."""
        query = parse_selector("function:nth(2)")
        assert query is not None
        assert len(query.first.pseudos) == 1
        assert query.first.pseudos[0].kind.value == "nth"
        assert query.first.pseudos[0].index == 2


class TestParserPredicateOperators:
    """Test predicate operators."""

    def test_parse_equals_operator(self):
        """Test parsing equals operator."""
        query = parse_selector("function[name='test']")
        assert query.first.predicates[0].op.value == "="

    def test_parse_not_equals_operator(self):
        """Test parsing not equals operator."""
        query = parse_selector("function[name!='test']")
        assert query.first.predicates[0].op.value == "!="

    def test_parse_contains_operator(self):
        """Test parsing contains operator."""
        query = parse_selector("function[name~='test']")
        assert query.first.predicates[0].op.value == "~="

    def test_parse_starts_with_operator(self):
        """Test parsing starts with operator."""
        query = parse_selector("function[name^='test']")
        assert query.first.predicates[0].op.value == "^="

    def test_parse_ends_with_operator(self):
        """Test parsing ends with operator."""
        query = parse_selector("function[name$='test']")
        assert query.first.predicates[0].op.value == "$="


class TestParserErrorHandling:
    """Test parser error handling."""

    def test_parse_empty_string(self):
        """Test parsing empty string raises error."""
        with pytest.raises(QueryParseError):
            parse_selector("")

    def test_parse_invalid_syntax(self):
        """Test parsing invalid syntax raises error."""
        with pytest.raises(QueryParseError):
            parse_selector("function[")

    def test_parse_invalid_predicate(self):
        """Test parsing invalid predicate raises error."""
        with pytest.raises(QueryParseError):
            parse_selector("function[name]")

    def test_parse_invalid_pseudo(self):
        """Test parsing invalid pseudo raises error."""
        # Parser may raise VisitError for unsupported pseudo
        with pytest.raises((QueryParseError, Exception)):
            parse_selector("function:invalid")

    def test_parse_invalid_nth(self):
        """Test parsing invalid nth pseudo raises error."""
        with pytest.raises(QueryParseError):
            parse_selector("function:nth()")


class TestParserComplexQueries:
    """Test complex query parsing."""

    def test_parse_complex_query(self):
        """Test parsing complex query."""
        query = parse_selector(
            "class[name='Test'] > function[name='test'] smallstmt[type='Return']:first"
        )
        assert query is not None
        assert len(query.rest) == 2  # Two additional steps after first

    def test_parse_nested_predicates(self):
        """Test parsing nested predicates."""
        query = parse_selector(
            "class[name='Test'][qualname='test.Test'] function[name='test']"
        )
        assert query is not None
        assert len(query.rest) == 1  # One additional step after first


class TestParserChainedDslash:
    """HRS {j003}: chained // descendant steps after a prior step."""

    def test_parse_chained_dslash_j003_selector(self):
        """parse_selector accepts the exact HRS {j003} selector string."""
        query = parse_selector(_HRS_J003_SELECTOR)
        assert query.first.node_type == "ClassDef"
        assert len(query.rest) == 1
        comb, step = query.rest[0]
        assert comb == Combinator.RECURSIVE_DESCENDANT
        assert step.node_type == "FunctionDef"
        assert len(step.predicates) == 2
        assert step.predicates[0].attr == "name"
        assert step.predicates[0].value == "execute"
        assert step.predicates[1].attr == "start_line"
        assert step.predicates[1].op.value == ">="
