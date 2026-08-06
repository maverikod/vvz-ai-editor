"""Selector language for the tree-query engine: AST, grammar, parser, error.

This module vendors the selector language into ``tree_engine`` so the
package is self-contained and installable on its own, depending on no
legacy package. It is a faithful PORT of the legacy ``cst_query`` AST and
Lark parser plus that package's query-parse exception: grammar, transformer
logic, accepted and rejected inputs, and error message text are carried
over verbatim. The legacy sources are untouched -- a copy, not a move.

Supported features: steps ``TYPE`` / ``TYPE:*`` / ``*``; combinators
descendant (space), direct child (``>``), recursive descendant (``//``);
predicates ``[attr OP value]`` / ``[@attr OP value]`` with string ops
``=``, ``!=``, ``~=`` (contains), ``^=`` (starts-with), ``$=`` (ends-with)
and numeric ops ``>``, ``<``, ``>=``, ``<=``; pseudos ``:first``,
``:last``, ``:nth(N)``, ``:not(selector)``. Values may be quoted or bare;
whitespace is insignificant except as the descendant combinator. Examples:
``function[name='foo']``, ``//FunctionDef[@name='foo']``,
``function[@name^='_']:not([name^='__'])``, ``class > method:first``,
``Def:*[name='run']``.

Error discipline: the legacy parser raised ``QueryParseError``, an
exception carrying the ad-hoc string code ``"QUERY_PARSE_ERROR"``. That
taxonomy does not exist here, but the frozen catalog in
:mod:`tree_engine.errors` already owns a code for exactly this condition --
``ErrorCode.INVALID_SELECTOR``, "a query/drill_down selector is malformed
or cannot be applied" -- so the ported exception is based on the project's
own hierarchy: it subclasses :class:`tree_engine.exceptions.InvalidSelector`
rather than inventing a new code. The legacy constructor signature and the
``.message``/``.details`` attributes are preserved, so call sites passing
``details={"error_code": ...}`` keep working unchanged. One consequence is
deliberate: ``TreeEngineException`` prefixes every message with its code,
so ``str(err)`` reads ``"[INVALID_SELECTOR] msg"`` where the legacy class
rendered the bare message (``.message`` still holds the bare text).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from lark import Lark, Transformer, Token, UnexpectedInput

from tree_engine.exceptions import InvalidSelector

__all__ = [
    "QueryParseError",
    "Combinator",
    "PredicateOp",
    "Predicate",
    "PseudoKind",
    "Pseudo",
    "SelectorStep",
    "Query",
    "parse_selector",
]


class QueryParseError(InvalidSelector):
    """Raised when a selector cannot be parsed or cannot be executed.

    Ported from the legacy query-parse exception and rebased onto this
    project's own error hierarchy: the stable catalog code is
    ``ErrorCode.INVALID_SELECTOR``, fixed by :class:`InvalidSelector` and
    never restated here. The legacy keyword arguments are kept so callers
    and call sites port over without edits.
    """

    def __init__(
        self,
        message: str,
        query_string: Optional[str] = None,
        parse_position: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize with the legacy arguments: the human-readable message,
        the optional offending query string, the optional character position
        the failure was detected at, and an optional extra-details dict."""
        super().__init__(message, **(details or {}))
        self.message = message
        self.query_string = query_string
        self.parse_position = parse_position


# --- Selector AST (ported from the legacy cst_query ``ast`` module) --------


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


# --- Grammar and parser (ported from the legacy cst_query ``parser``) ------

_GRAMMAR = r"""
?start: selector

selector: dslash_step ((CHILD step) | dslash_step | step)*
        | step ((CHILD step) | dslash_step | step)*
CHILD: ">"
DSLASH: "//"

dslash_step: DSLASH step

step: node_type predicate* pseudo*
    | predicate+ pseudo*
    | pseudo+
node_type: STAR | NAME type_wildcard?
type_wildcard: ":*"
STAR: "*"

predicate: "[" AT? NAME OP value "]"
AT: "@"
OP: ">=" | "<=" | "!=" | "~=" | "^=" | "$=" | ">" | "<" | "="
?value: STRING | BAREWORD

pseudo: ":" NAME pseudo_args?
pseudo_args: "(" INT ")"
           | "(" selector ")"

NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
BAREWORD: /[^\]\s\)]+/
INT: /[0-9]+/

%import common.ESCAPED_STRING -> STRING
%import common.WS_INLINE -> WS
%ignore WS
"""


_parser = Lark(_GRAMMAR, parser="lalr", start="start")


@dataclass(frozen=True)
class _ParsedPseudo:
    name: str
    index: Optional[int]
    not_query: Optional["Query"] = None


class _ToAst(Transformer):
    """Lark transformer: converts parse tree into CSTQuery AST nodes."""

    def NAME(self, t: Token) -> str:  # noqa: N802
        return str(t)

    def INT(self, t: Token) -> int:  # noqa: N802
        return int(str(t))

    def STAR(self, _t: Token) -> str:  # noqa: N802
        return "*"

    def BAREWORD(self, t: Token) -> str:  # noqa: N802
        """Parse bareword value, handling quoted strings that were parsed as barewords.

        Sometimes quoted strings (especially single quotes inside double-quoted
        Python strings) are parsed as BAREWORD instead of STRING.
        We need to detect and handle these cases.
        """
        raw = str(t)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            unquoted = raw[1:-1]
            try:
                return bytes(unquoted, "utf-8").decode("unicode_escape")
            except (UnicodeDecodeError, UnicodeError):
                return unquoted
        return raw

    def STRING(self, t: Token) -> str:  # noqa: N802
        """Parse string value, removing quotes and handling escape sequences.

        Lark provides the string token with quotes included.
        We need to remove the outer quotes and decode escape sequences.
        """
        raw = str(t)
        if len(raw) >= 2:
            if raw[0] == raw[-1] and raw[0] in ("'", '"'):
                unquoted = raw[1:-1]
                try:
                    return bytes(unquoted, "utf-8").decode("unicode_escape")
                except (UnicodeDecodeError, UnicodeError):
                    return unquoted
        return raw

    def OP(self, t: Token) -> str:  # noqa: N802
        return str(t)

    def predicate(self, items: list[Any]) -> Predicate:
        """Build Predicate; strip optional AT token before attr name."""
        filtered = [
            it for it in items if not (isinstance(it, Token) and it.type == "AT")
        ]
        attr, op_str, value = str(filtered[0]), str(filtered[1]), str(filtered[2])
        return Predicate(attr=attr, op=PredicateOp(op_str), value=value)

    def dslash_step(self, items: list[Any]) -> tuple[Combinator, SelectorStep]:
        """Transform //step into (RECURSIVE_DESCENDANT, inner step).

        Leading ``//`` starts a recursive descendant search from the tree root;
        a chained ``//`` after a prior step applies the same combinator between
        steps (e.g. ``//ClassDef//FunctionDef``).
        """
        inner = next((it for it in items if isinstance(it, SelectorStep)), None)
        if inner is None:
            raise QueryParseError("dslash_step: expected SelectorStep")
        return (Combinator.RECURSIVE_DESCENDANT, inner)

    def pseudo_args(self, items: list[Any]) -> Any:
        """Return INT for :nth or Query for :not; else first item."""
        if items and isinstance(items[0], int):
            return items[0]
        if items and isinstance(items[0], Query):
            return items[0]
        return items[0] if items else None

    def pseudo(self, items: list[Any]) -> _ParsedPseudo:
        """Build _ParsedPseudo from parsed pseudo token and optional arg."""
        name = str(items[0])
        arg = items[1] if len(items) > 1 else None
        if isinstance(arg, int):
            return _ParsedPseudo(name=name, index=arg)
        if isinstance(arg, Query):
            return _ParsedPseudo(name=name, index=None, not_query=arg)
        return _ParsedPseudo(name=name, index=None)

    def node_type(self, items: list[Any]) -> str:
        """Build node type string, appending ':*' for wildcard suffix."""
        name = str(items[0])
        if len(items) > 1:
            return name + ":*"
        return name

    def step(self, items: list[Any]) -> SelectorStep:
        """Build SelectorStep from node_type, predicates, pseudos and :not."""
        node_type: str = "*"
        predicates: list[Predicate] = []
        pseudos: list[Pseudo] = []
        not_selector: Any = None
        for it in items:
            if isinstance(it, str):
                node_type = it
            elif isinstance(it, Predicate):
                predicates.append(it)
            elif isinstance(it, _ParsedPseudo):
                p = _pseudo_from_parsed(it)
                if p.kind == PseudoKind.NOT:
                    not_selector = it.not_query
                else:
                    pseudos.append(p)
            else:
                raise QueryParseError(f"Unexpected step item: {it!r}")
        return SelectorStep(
            node_type=node_type,
            predicates=tuple(predicates),
            pseudos=tuple(pseudos),
            not_selector=not_selector,
        )

    def selector(self, items: list[Any]) -> Query:
        """Build Query from parsed steps and combinators."""
        if not items:
            raise QueryParseError("Empty selector")
        first_item = items[0]
        if isinstance(first_item, tuple):
            _leading_comb, first = first_item
            if not isinstance(first, SelectorStep):
                raise QueryParseError("Invalid selector start")
        elif isinstance(first_item, SelectorStep):
            first = first_item
        else:
            raise QueryParseError("Invalid selector start")
        rest: list[tuple[Combinator, SelectorStep]] = []
        i = 1
        while i < len(items):
            it = items[i]
            if isinstance(it, Token) and it.type == "CHILD":
                step = items[i + 1]
                if not isinstance(step, SelectorStep):
                    raise QueryParseError("Invalid selector sequence")
                rest.append((Combinator.CHILD, step))
                i += 2
                continue
            if isinstance(it, tuple):
                comb, step = it
                if not isinstance(step, SelectorStep):
                    raise QueryParseError("Invalid selector sequence")
                rest.append((comb, step))
                i += 1
                continue
            if isinstance(it, SelectorStep):
                rest.append((Combinator.DESCENDANT, it))
                i += 1
                continue
            raise QueryParseError("Invalid selector sequence")
        return Query(first=first, rest=tuple(rest))


def _pseudo_from_parsed(p: _ParsedPseudo) -> Pseudo:
    name = p.name.lower()
    if name == PseudoKind.FIRST.value:
        if p.index is not None:
            raise QueryParseError(":first does not accept arguments")
        return Pseudo(kind=PseudoKind.FIRST)
    if name == PseudoKind.LAST.value:
        if p.index is not None:
            raise QueryParseError(":last does not accept arguments")
        return Pseudo(kind=PseudoKind.LAST)
    if name == PseudoKind.NTH.value:
        if not isinstance(p.index, int):
            raise QueryParseError(":nth requires an integer argument, e.g. :nth(0)")
        return Pseudo(kind=PseudoKind.NTH, index=p.index)
    if name == PseudoKind.NOT.value:
        return Pseudo(kind=PseudoKind.NOT)
    raise QueryParseError(f"Unsupported pseudo: {p.name}")


def parse_selector(selector: str) -> Query:
    """
    Parse a selector into a CSTQuery AST.

    Raises:
        QueryParseError
    """
    try:
        tree = _parser.parse(selector)
        return _ToAst().transform(tree)
    except UnexpectedInput as e:
        raise QueryParseError(f"Invalid selector: {e}") from e
