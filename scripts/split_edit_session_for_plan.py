#!/usr/bin/env python3
"""Build edit_session_impl.py and edit_session_mutations.py for plan AS prompts."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "ai_editor/core/edit_session/edit_session.py").read_text().splitlines()

checkout = next(i for i, l in enumerate(SRC) if l.strip().startswith("def checkout_history_index"))
export = next(i for i, l in enumerate(SRC) if l.strip().startswith("def _export_source_via_unmark"))
get_active = next(i for i, l in enumerate(SRC) if l.strip().startswith("def get_active_session"))

HEAD = SRC[:checkout]
LIFECYCLE = SRC[checkout:export]
HELPERS = SRC[export:get_active]


def method_to_func(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.startswith("    def "):
            m = re.match(r"    def (\w+)\(self(.*)\)", line)
            if not m:
                out.append(line)
                continue
            name, rest = m.group(1), m.group(2)
            out.append(f"def {name}(session: EditSession{rest}):")
        elif line.startswith("        "):
            out.append("    " + line[8:].replace("self.", "session."))
        else:
            out.append(line)
    return out


def build_mutations() -> str:
    parts = [
        '"""EditSession lifecycle and tree helper functions (C-019).',
        "",
        "Author: Vasiliy Zdanovskiy",
        "email: vasilyvz@gmail.com",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import difflib",
        "import os",
        "import shutil",
        "from pathlib import Path",
        "from typing import TYPE_CHECKING, Any",
        "",
        "from ai_editor.core.tree_lifecycle import compute_content_checksum",
        "from ai_editor.core.tree_lifecycle.node_id_map import (",
        "    ChecksumsSection,",
        "    DiscoveredNode,",
        "    NodeIdMap,",
        "    compute_content_fingerprint,",
        "    parse_tree_file,",
        "    serialize_tree_file,",
        ")",
        "from ai_editor.tree.handler_registry import HandlerRegistry",
        "",
        "if TYPE_CHECKING:",
        "    from .edit_session_impl import EditSession, SessionTreeValidity",
        "",
    ]
    parts.extend(method_to_func(LIFECYCLE + HELPERS))
    return "\n".join(parts).rstrip() + "\n"


def build_impl() -> str:
    head = list(HEAD)
    # wire private helpers to mutations module
    repl = {
        "self._export_source_via_unmark()": "_mut.export_source_via_unmark(self)",
        "self._update_session_tree_checksums(": "_mut.update_session_tree_checksums(session=self, ",
        "self._build_session_tree(": "_mut.build_session_tree(session, ",
        "self._try_revalidate()": "_mut.try_revalidate(self)",
    }
    for i, line in enumerate(head):
        for old, new in repl.items():
            if old in line:
                head[i] = line.replace("self._update_session_tree_checksums(", new)
                if "session=self" in head[i]:
                    head[i] = head[i].replace("session=self, ", "")
                    head[i] = head[i].replace(
                        "_mut.update_session_tree_checksums(",
                        "_mut.update_session_tree_checksums(self, ",
                    )
                break

    # simpler: replace in joined text
    text = "\n".join(HEAD)
    text = text.replace("self._export_source_via_unmark()", "_mut.export_source_via_unmark(self)")
    text = text.replace(
        "self._update_session_tree_checksums(self.source_checksum)",
        "_mut.update_session_tree_checksums(self, self.source_checksum)",
    )
    text = text.replace("self._build_session_tree(source_text)", "_mut.build_session_tree(self, source_text)")
    text = text.replace("self._try_revalidate()", "_mut.try_revalidate(self)")

    idx = text.index("class EditSession")
    text = text[:idx] + text[idx:]

    delegates = """

    def checkout_history_index(self, index: int) -> None:
        _mut.checkout_history_index(self, index)

    def undo(self) -> dict[str, object]:
        return _mut.undo(self)

    def redo(self) -> dict[str, object]:
        return _mut.redo(self)

    def record_revert_commit(self, *, rev: str) -> str:
        return _mut.record_revert_commit(self, rev=rev)

    def preview_external_write(self) -> dict[str, Any]:
        return _mut.preview_external_write(self)

    def confirm_external_copy_out(self) -> None:
        _mut.confirm_external_copy_out(self)

    def close(self) -> None:
        _mut.close(self)

    def record_tree_modification(self) -> None:
        _mut.record_tree_modification(self)
"""
    return text.rstrip() + delegates + "\n\nfrom . import edit_session_mutations as _mut\n"


def rename_mutations(mutations: str) -> str:
    mutations = mutations.replace("def _export_source_via_unmark", "def export_source_via_unmark")
    mutations = mutations.replace("def _update_session_tree_checksums", "def update_session_tree_checksums")
    mutations = mutations.replace("def _build_session_tree", "def build_session_tree")
    mutations = mutations.replace("def _try_revalidate", "def try_revalidate")
    mutations = mutations.replace(
        "def close(session: EditSession)",
        "def close(session: \"EditSession\")",
    )
    mutations = re.sub(
        r"(def close\(session[^\n]*\):\n)(    _active_sessions)",
        r"\1    from .edit_session_impl import _active_sessions\n\n    _active_sessions",
        mutations,
        count=1,
    )
    return mutations


if __name__ == "__main__":
    mut = rename_mutations(build_mutations())
    impl = build_impl()
    print("impl", len(impl.splitlines()), "mut", len(mut.splitlines()))
