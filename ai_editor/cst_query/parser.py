"""
CSTQuery selector parser (Lark).

Supported features:
- Steps: `TYPE`, `TYPE:*` (prefix/suffix match on node type), or `*`
- Combinators: descendant (space), direct child (`>`), recursive descendant (`//`)
- Predicates: [attr OP value] or [@attr OP value] (@ prefix is optional)
  - String ops: =, !=, ~= (contains), ^= (starts-with), $= (ends-with)
  - Numeric ops: >, <, >=, <= (for start_line, end_line, children_count)
- Pseudos: :first, :last, :nth(N), :not(selector)

Type modifier `:*` matches by prefix or suffix: e.g. `Def:*` -> FunctionDef, ClassDef.

Available attributes for predicates:
  name, qualname, type, kind, start_line, end_line, children_count, module

Examples:
  function[name='foo']                     # function named foo
  //FunctionDef[@name='foo']               # same, XPath-style with // and @
  function[start_line>=100]                # functions starting at line 100+
  function[@name^='_']:not([name^='__'])   # private but not dunder functions
  class > method:first                     # first method of each class
  Def:*[name='run']                        # FunctionDef or ClassDef named run

Notes:
- Values can be quoted with single or double quotes; unquoted barewords are allowed.
- Whitespace is insignificant except as descendant combinator.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


from dataclasses import dataclass


from typing import Any, Optional


from lark import Lark, Transformer, Token, UnexpectedInput


from .ast import (
    Combinator,
    Predicate,
    PredicateOp,
    Pseudo,
    PseudoKind,
    Query,
    SelectorStep,
)


from ..core.exceptions import QueryParseError

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
