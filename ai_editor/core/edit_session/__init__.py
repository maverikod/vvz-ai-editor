# Author: Vasiliy Zdanovskiy -- vasilyvz@gmail.com

"""EditSession package (C-012): bounded editing context and active-session registry."""

from ai_editor.core.edit_session.edit_session import (
    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,
    EditSession,
    EditSessionError,
    SESSION_INVALID_TRUTH_INVARIANT,
    SESSION_VALID_TRUTH_INVARIANT,
    SessionTreeValidity,
    get_active_session,
)
from ai_editor.core.edit_session.session_repo import (
    ONE_COMMIT_PER_MUTATION_INVARIANT,
    SessionCommit,
    SessionRepo,
)

__all__ = [
    "EditSession",
    "EditSessionError",
    "SessionTreeValidity",
    "get_active_session",
    "CONTENT_NOT_ALLOWED_FOR_VALID_FILE",
    "SESSION_VALID_TRUTH_INVARIANT",
    "SESSION_INVALID_TRUTH_INVARIANT",
    "SessionRepo",
    "SessionCommit",
    "ONE_COMMIT_PER_MUTATION_INVARIANT",
]
