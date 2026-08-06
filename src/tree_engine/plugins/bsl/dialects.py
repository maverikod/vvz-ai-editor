"""BSL/1C keyword dialect tables and normalization helpers (concept C-015).

BSL ("1C:Enterprise" built-in language) is written in one of two keyword
dialects -- Russian or English -- chosen per source document, never mixed
within a construct. Both dialects are recognized on IMPORT and a document's
own dialect is restored exactly on generation, by a single translator
({p047}: "Russian and English keywords are supported by one translator").
This module is the single source of truth for that mapping: it owns every
BSL keyword spelling and every annotation prefix spelling, in both
dialects, plus the pure normalization functions that convert between a raw
written token and a canonical, dialect-independent construct label.

Covered constructs, per the governing HRS fragments:

* the procedure keyword (``Процедура`` / ``Procedure``, {p047});
* the function keyword (``Функция`` / ``Function``, {p047});
* the export keyword (``Экспорт`` / ``Export``, {p044}, {p047});
* the variable-declaration keyword (``Перем`` / ``Var``, {iblr}, {p047});
* the ``Знач``/``Val`` by-value parameter passing-mode modifier ({p115});
* annotation prefixes such as ``&НаСервере``/``&AtServer`` and
  ``&НаКлиенте``/``&AtClient`` ({an01}, {p047}).

Non-goals, per this step's brief: this module defines no tree-sitter
integration, no format-plugin machinery, and no common-model node
construction. It is pure keyword data and string normalization, usable as-
is by ``import_map.py`` (BSL source text -> common model, a sibling not yet
merged) and ``generator.py`` (common model -> BSL source text, a sibling
not yet merged) so neither one hard-codes its own copy of these keyword
strings. It depends only on the standard library.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Mapping, Optional

__all__ = [
    "Dialect",
    "RUSSIAN",
    "ENGLISH",
    "DIALECTS",
    "PROCEDURE",
    "FUNCTION",
    "EXPORT",
    "VAR",
    "BY_VALUE",
    "RUSSIAN_KEYWORDS",
    "ENGLISH_KEYWORDS",
    "AT_SERVER",
    "AT_CLIENT",
    "AT_SERVER_NO_CONTEXT",
    "AT_CLIENT_AT_SERVER_NO_CONTEXT",
    "ANNOTATION_PREFIXES",
    "normalize_dialect",
    "get_canonical_keyword",
    "keyword_for_target_dialect",
    "is_by_value_modifier",
    "is_annotation_prefix",
    "get_annotation_form",
]

# ---------------------------------------------------------------------------
# Dialects
# ---------------------------------------------------------------------------

#: A dialect label is always one of the two canonical strings below; kept as
#: a plain ``str`` alias (not an ``enum``) so it composes cheaply with the
#: common model's own plain-string field values.
Dialect = str

RUSSIAN: Dialect = "russian"
ENGLISH: Dialect = "english"

#: Every recognized canonical dialect label, for validation and iteration.
DIALECTS: FrozenSet[Dialect] = frozenset({RUSSIAN, ENGLISH})

# Aliases a caller (a CLI flag, a document-metadata field, ...) might supply
# for "Russian" or "English"; deliberately generous so callers never have to
# guess the one true spelling. Keys are matched case-insensitively.
_DIALECT_ALIASES: Mapping[str, Dialect] = {
    "russian": RUSSIAN,
    "ru": RUSSIAN,
    "rus": RUSSIAN,
    "ru-ru": RUSSIAN,
    "русский": RUSSIAN,
    "рус": RUSSIAN,
    "english": ENGLISH,
    "en": ENGLISH,
    "eng": ENGLISH,
    "en-us": ENGLISH,
    "английский": ENGLISH,
    "англ": ENGLISH,
}


def normalize_dialect(name: str) -> Dialect:
    """Map a user-provided dialect name to the canonical ``russian`` or
    ``english`` label.

    Matching is case- and whitespace-insensitive and accepts the common
    aliases in :data:`_DIALECT_ALIASES` (``"ru"``, ``"en"``, the Russian
    words for the dialect names, ...), so callers never need to guess which
    exact spelling this module expects.

    Raises :class:`ValueError` if ``name`` is not a recognized dialect.
    """

    if not isinstance(name, str):
        raise ValueError(f"dialect name must be a str, got {type(name).__name__}")
    key = name.strip().lower()
    if key in DIALECTS:
        return key
    try:
        return _DIALECT_ALIASES[key]
    except KeyError:
        raise ValueError(f"unknown BSL dialect: {name!r}") from None


# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

# Canonical, dialect-independent construct labels. These are the shared
# representation every dialect's written keyword normalizes to, and the
# lookup key ``keyword_for_target_dialect`` accepts to render a keyword back
# into a chosen dialect's written form.
PROCEDURE = "procedure"
FUNCTION = "function"
EXPORT = "export"
VAR = "var"
BY_VALUE = "by_value"

#: Russian dialect keyword table: canonical label -> written Russian form.
RUSSIAN_KEYWORDS: Mapping[str, str] = {
    PROCEDURE: "Процедура",
    FUNCTION: "Функция",
    EXPORT: "Экспорт",
    VAR: "Перем",
    BY_VALUE: "Знач",
}

#: English dialect keyword table: canonical label -> written English form.
ENGLISH_KEYWORDS: Mapping[str, str] = {
    PROCEDURE: "Procedure",
    FUNCTION: "Function",
    EXPORT: "Export",
    VAR: "Var",
    BY_VALUE: "Val",
}

_KEYWORD_TABLES: Mapping[Dialect, Mapping[str, str]] = {
    RUSSIAN: RUSSIAN_KEYWORDS,
    ENGLISH: ENGLISH_KEYWORDS,
}

# Reverse lookup per dialect, built once: lower-cased written form ->
# canonical label. BSL keywords are themselves case-insensitive in 1C, so
# normalization is case-insensitive on the written side.
_KEYWORD_REVERSE: Dict[Dialect, Dict[str, str]] = {
    dialect: {written.lower(): canonical for canonical, written in table.items()}
    for dialect, table in _KEYWORD_TABLES.items()
}

# Flat set of every by-value modifier spelling (both dialects), lower-cased,
# for case-insensitive membership tests independent of which dialect a
# caller happens to be working in.
_BY_VALUE_TOKENS: FrozenSet[str] = frozenset(
    table[BY_VALUE].lower() for table in _KEYWORD_TABLES.values()
)


def get_canonical_keyword(token: str, dialect: Dialect) -> Optional[str]:
    """Normalize a raw keyword token written in ``dialect`` to its
    canonical, dialect-independent construct label (one of
    :data:`PROCEDURE`, :data:`FUNCTION`, :data:`EXPORT`, :data:`VAR`,
    :data:`BY_VALUE`).

    Matching is case-insensitive, mirroring BSL's own case-insensitive
    keywords. Returns ``None`` when ``token`` is not a recognized keyword in
    ``dialect`` -- this is a lookup miss, not an error, since callers use it
    to probe arbitrary source tokens.
    """

    resolved = normalize_dialect(dialect)
    return _KEYWORD_REVERSE[resolved].get(token.strip().lower())


def keyword_for_target_dialect(canonical: str, dialect: Dialect) -> str:
    """Map a canonical keyword label back to its written form in
    ``dialect``.

    This is the inverse of :func:`get_canonical_keyword`: for any
    ``canonical`` in {:data:`PROCEDURE`, :data:`FUNCTION`, :data:`EXPORT`,
    :data:`VAR`, :data:`BY_VALUE`}, ``get_canonical_keyword`` applied to
    this function's own result (in the same dialect) returns ``canonical``
    again unchanged -- the round trip {p047}/{p115} generation relies on.

    Raises :class:`ValueError` if ``canonical`` is not a known canonical
    keyword label.
    """

    resolved = normalize_dialect(dialect)
    table = _KEYWORD_TABLES[resolved]
    try:
        return table[canonical]
    except KeyError:
        raise ValueError(f"unknown canonical BSL keyword: {canonical!r}") from None


def is_by_value_modifier(token: str) -> bool:
    """Identify whether ``token`` is the by-value parameter passing-mode
    modifier -- ``Знач`` in the Russian dialect or ``Val`` in the English
    dialect ({p115}) -- in either dialect and in any case variant.

    Deliberately dialect-agnostic (unlike :func:`get_canonical_keyword`,
    which requires the caller to already know the dialect): a parameter
    list is scanned token-by-token before its document's dialect need be
    settled, so both spellings are checked at once.
    """

    return token.strip().lower() in _BY_VALUE_TOKENS


# ---------------------------------------------------------------------------
# Annotation prefixes
# ---------------------------------------------------------------------------

# Canonical, dialect-independent annotation labels. Kept as a table
# separate from the plain-keyword table above: annotations are a distinct
# BSL construct ({an01}) with their own written forms, never merged with
# the procedure/function/export/var/by-value keyword set.
AT_SERVER = "at_server"
AT_CLIENT = "at_client"
AT_SERVER_NO_CONTEXT = "at_server_no_context"
AT_CLIENT_AT_SERVER_NO_CONTEXT = "at_client_at_server_no_context"

#: Canonical annotation label -> {dialect -> written form}. The Russian
#: ampersand-``На`` forms and the English ampersand-``At`` forms are the two
#: canonical written variants ({p047}); every entry covers both.
ANNOTATION_PREFIXES: Mapping[str, Mapping[Dialect, str]] = {
    AT_SERVER: {RUSSIAN: "&НаСервере", ENGLISH: "&AtServer"},
    AT_CLIENT: {RUSSIAN: "&НаКлиенте", ENGLISH: "&AtClient"},
    AT_SERVER_NO_CONTEXT: {
        RUSSIAN: "&НаСервереБезКонтекста",
        ENGLISH: "&AtServerNoContext",
    },
    AT_CLIENT_AT_SERVER_NO_CONTEXT: {
        RUSSIAN: "&НаКлиентеНаСервереБезКонтекста",
        ENGLISH: "&AtClientAtServerNoContext",
    },
}

# Reverse lookup: lower-cased written form (either dialect) -> canonical
# annotation label, built once for O(1) matching.
_ANNOTATION_REVERSE: Dict[str, str] = {
    written.lower(): canonical
    for canonical, forms in ANNOTATION_PREFIXES.items()
    for written in forms.values()
}


def is_annotation_prefix(token: str, dialect: Optional[Dialect] = None) -> Optional[str]:
    """Match ``token`` against the known BSL annotation prefixes in either
    dialect (``&НаСервере``/``&AtServer``, ``&НаКлиенте``/``&AtClient``,
    ...), per {an01}/{p047}.

    Matching is case-insensitive. Returns the matched canonical annotation
    label (e.g. :data:`AT_SERVER`) on a hit -- truthy and directly usable as
    the dialect-independent value to store on an annotation node -- or
    ``None`` on a miss. Pass ``dialect`` to require the match to come from
    that specific dialect's written forms only; omit it (the default) to
    match either dialect, which is what a translator that has not yet
    settled a document's dialect needs.
    """

    normalized = token.strip().lower()
    if dialect is None:
        return _ANNOTATION_REVERSE.get(normalized)
    resolved = normalize_dialect(dialect)
    for canonical, forms in ANNOTATION_PREFIXES.items():
        if forms[resolved].lower() == normalized:
            return canonical
    return None


def get_annotation_form(canonical: str, dialect: Dialect) -> str:
    """Render the annotation identified by ``canonical`` (e.g.
    :data:`AT_SERVER`) in its written form for ``dialect``.

    This is the inverse of :func:`is_annotation_prefix`: for any known
    ``canonical``, ``is_annotation_prefix`` applied to this function's own
    result (restricted to the same ``dialect``) returns ``canonical``
    again unchanged, the round trip code generation relies on to restore a
    document's own annotation dialect exactly ({p047}, {p105}).

    Raises :class:`ValueError` if ``canonical`` is not a known canonical
    annotation label.
    """

    resolved = normalize_dialect(dialect)
    try:
        return ANNOTATION_PREFIXES[canonical][resolved]
    except KeyError:
        raise ValueError(f"unknown canonical BSL annotation: {canonical!r}") from None
