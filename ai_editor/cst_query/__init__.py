"""
CSTQuery - jQuery/XPath-like selectors for Python code (LibCST).

This package is designed as a standalone component that can be extracted into a
separate library if needed.

Public API:
  - parse_selector(selector: str) -> Query
  - query_source(source: str, selector: str, *, include_code: bool = False) -> list[Match]
  - QueryParseError

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ..core.exceptions import QueryParseError
from .ast import (
    Combinator,
    Predicate,
    Pseudo,
    Query,
    SelectorStep,
)
from .parser import parse_selector
from .executor import Match, query_source

__all__ = [
    "QueryParseError",
    "Combinator",
    "Predicate",
    "Pseudo",
    "Query",
    "SelectorStep",
    "parse_selector",
    "Match",
    "query_source",
]
