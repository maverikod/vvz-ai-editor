"""
CSTQuery AST models.

These data structures represent a parsed selector query.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


from dataclasses import dataclass

from enum import Enum

from typing import Optional


class Combinator(str, Enum):
    """Selector step relation."""

    DESCENDANT = " "
    CHILD = ">"
    RECURSIVE_DESCENDANT = "//"


class PredicateOp(str, Enum):
    """Predicate operator for attribute tests."""

    EQ = "="
    NE = "!="
    CONTAINS = "~="
    PREFIX = "^="
    SUFFIX = "$="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="


@dataclass(frozen=True)
class Predicate:
    """Attribute predicate like [name="foo"] or [qualname^="A.B"]."""

    attr: str
    op: PredicateOp
    value: str


class PseudoKind(str, Enum):
    """Pseudo-class / functional pseudo."""

    FIRST = "first"
    LAST = "last"
    NTH = "nth"
    NOT = "not"


@dataclass(frozen=True)
class Pseudo:
    """Pseudo like :first, :last, :nth(0)."""

    kind: PseudoKind
    index: Optional[int] = None


@dataclass(frozen=True)
class SelectorStep:
    """
    A single selector step.

    `node_type` can be:
    - "*" (match anything)
    - alias: module, class, function, method, stmt, smallstmt, import
    - LibCST node class name (e.g. If, For, Try, With, Return)
    - "Type:*" for prefix/suffix match (e.g. Def:* -> FunctionDef, ClassDef)
    """

    node_type: str
    predicates: tuple[Predicate, ...] = ()
    pseudos: tuple[Pseudo, ...] = ()
    not_selector: Optional["Query"] = None


@dataclass(frozen=True)
class Query:
    """A full query, e.g. class[name="A"] > function[name="m"] stmt[type="If"]."""

    first: SelectorStep
    rest: tuple[tuple[Combinator, SelectorStep], ...] = ()
