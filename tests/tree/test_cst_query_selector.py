"""
Tests for CstQuerySelector.parse validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest

from ai_editor.cst_query import parse_selector, query_source
from ai_editor.tree.cst_query_selector import (
    CstQuerySelector,
    CstQuerySelectorError,
)

_HRS_J003_SELECTOR = "//ClassDef//FunctionDef[@name='execute'][start_line>=100]"

_ACCEPT_SELECTORS = (
    "function[name='foo']",
    "function[start_line>=100]",
    _HRS_J003_SELECTOR,
    ":not(function)",
)

_REJECT_SELECTORS = (
    "function[node_id='a1b2c3d4-e5f6-7890-abcd-ef1234567890']",
    "//ClassDef//FunctionDef[12345678-1234-5678-9abc-def012345678]",
)


class TestCstQuerySelectorParse:
    """Parse accept/reject matrix aligned with CSTQuery parse_selector."""

    @pytest.mark.parametrize("selector", _ACCEPT_SELECTORS)
    def test_parse_accepts_engine_valid_selectors(self, selector: str) -> None:
        parsed = CstQuerySelector.parse(selector)
        assert parsed.selector == selector

    @pytest.mark.parametrize("selector", _REJECT_SELECTORS)
    def test_parse_rejects_uuid_in_selector(self, selector: str) -> None:
        with pytest.raises(CstQuerySelectorError, match="UUID node references"):
            CstQuerySelector.parse(selector)


class TestCstQuerySelectorJ003ChainedDslash:
    """HRS {j003}: chained // descendant steps."""

    def test_parse_selector_accepts_hrs_j003_selector(self) -> None:
        query = parse_selector(_HRS_J003_SELECTOR)
        assert query.first.node_type == "ClassDef"
        assert len(query.rest) == 1
        comb, step = query.rest[0]
        assert comb.value == "//"
        assert step.node_type == "FunctionDef"
        assert len(step.predicates) == 2
        assert step.predicates[0].attr == "name"
        assert step.predicates[0].value == "execute"
        assert step.predicates[1].attr == "start_line"
        assert step.predicates[1].op.value == ">="

    def test_query_source_hrs_j003_selector(self) -> None:
        lines = ["# filler"] * 98
        lines.extend(
            [
                "class Outer:",
                "    def execute(self):",
                "        pass",
            ]
        )
        source = "\n".join(lines)
        matches = query_source(source, _HRS_J003_SELECTOR)
        assert len(matches) == 1
        assert matches[0].node_type == "FunctionDef"
        assert matches[0].name == "execute"
        assert matches[0].start_line >= 100
        assert matches[0].qualname == "Outer.execute"
