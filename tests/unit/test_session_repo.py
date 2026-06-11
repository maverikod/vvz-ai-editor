"""
Unit tests for SessionRepo per-mutation git history (C-013).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_editor.core.edit_session.session_repo import SessionRepo


def _write_pair(
    repo_dir: Path,
    source_name: str,
    tree_name: str,
    source_text: str,
    tree_text: str,
) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / source_name).write_text(source_text, encoding="utf-8")
    (repo_dir / tree_name).write_text(tree_text, encoding="utf-8")


def test_init_full_commit_captures_tree_and_source(tmp_path: Path) -> None:
    source_name = "demo.json"
    tree_name = "demo.json.tree"
    repo_dir = tmp_path / "repo_full"
    _write_pair(
        repo_dir,
        source_name,
        tree_name,
        '{"a":1}\n',
        "---CHECKSUMS---\ntree-v1\n",
    )
    repo = SessionRepo.init(
        repo_dir=repo_dir,
        source_name=source_name,
        tree_name=tree_name,
        include_tree=True,
        source_abs=repo_dir / source_name,
    )
    commits = repo.log()
    assert len(commits) == 1
    assert commits[0].message == "session: initial commit"
    shown_source = repo.show_source(rev=commits[0].hash).decode("utf-8")
    assert shown_source == '{"a":1}\n'
    shown_tree = repo.show_tree(rev=commits[0].hash).decode("utf-8")
    assert "tree-v1" in shown_tree


def test_commit_degraded_source_only(tmp_path: Path) -> None:
    source_name = "demo.json"
    tree_name = "demo.json.tree"
    repo_dir = tmp_path / "repo_deg"
    _write_pair(
        repo_dir,
        source_name,
        tree_name,
        "broken\n",
        "ignored\n",
    )
    repo = SessionRepo.init(
        repo_dir=repo_dir,
        source_name=source_name,
        tree_name=tree_name,
        include_tree=False,
        source_abs=repo_dir / source_name,
    )
    assert len(repo.log()) == 1
    assert repo.log()[0].message == "session: initial commit (degraded)"
    head = repo.log()[0].hash
    assert repo.show_source(rev=head).decode("utf-8") == "broken\n"


def test_two_mutations_two_commits(tmp_path: Path) -> None:
    source_name = "demo.json"
    tree_name = "demo.json.tree"
    repo_dir = tmp_path / "repo_mut"
    _write_pair(
        repo_dir,
        source_name,
        tree_name,
        '{"v":1}\n',
        "tree-a\n",
    )
    repo = SessionRepo.init(
        repo_dir=repo_dir,
        source_name=source_name,
        tree_name=tree_name,
        include_tree=True,
        source_abs=repo_dir / source_name,
    )
    (repo_dir / source_name).write_text('{"v":2}\n', encoding="utf-8")
    (repo_dir / tree_name).write_text("tree-b\n", encoding="utf-8")
    repo.commit_full(message="session: mutation 1")
    (repo_dir / tree_name).write_text("tree-c\n", encoding="utf-8")
    repo.commit_full(message="session: mutation 2")
    assert len(repo.log()) == 3
    messages = [entry.message for entry in repo.log()]
    assert messages == [
        "session: mutation 2",
        "session: mutation 1",
        "session: initial commit",
    ]


def test_revert_adds_new_commit_not_reset(tmp_path: Path) -> None:
    source_name = "demo.json"
    tree_name = "demo.json.tree"
    repo_dir = tmp_path / "repo_rev"
    _write_pair(
        repo_dir,
        source_name,
        tree_name,
        '{"x":1}\n',
        "tree-initial\n",
    )
    repo = SessionRepo.init(
        repo_dir=repo_dir,
        source_name=source_name,
        tree_name=tree_name,
        include_tree=True,
        source_abs=repo_dir / source_name,
    )
    initial_hash = repo.log()[0].hash
    (repo_dir / tree_name).write_text("tree-changed\n", encoding="utf-8")
    repo.commit_full(message="session: mutation")
    count_before = len(repo.log())
    assert count_before == 2
    new_hash = repo.revert(rev=initial_hash)
    count_after = len(repo.log())
    assert count_after == count_before + 1
    assert new_hash != initial_hash
    assert repo.show_tree(rev=new_hash).decode("utf-8") == "tree-initial\n"
