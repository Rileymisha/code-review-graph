"""Tests for GraphStore commit-intent ingest interface (Task 2 + Task 3).

These tests exercise:
* Task 2 — commit node CRUD + reverse/forward queries that ``GraphStore``
  exposes on top of the ``commits`` + ``commit_modifies_file`` tables added
  by migration v10.
* Task 3 — ``commit_ingest`` parser + ``ingest_commits`` end-to-end ingest
  against a real (tempdir) git repo.

Notes for implementer (vs. brief):
* ``GraphStore._conn`` is an attribute (sqlite3.Connection), not a callable.
* ``link_commit_to_file`` does NOT require a row in any ``files`` table —
  migration v10 dropped the phantom FK to ``files(path)``. The tests only
  insert into ``commit_modifies_file`` (directly or via the method).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from code_review_graph.commit_ingest import (
    GIT_LOG_FORMAT,
    MESSAGE_MAX_CHARS,
    ingest_commits,
    parse_git_log,
    truncate_message,
)
from code_review_graph.graph import CommitMetadata, GraphStore


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    # GraphStore.__init__ runs _init_schema() + run_migrations() already,
    # so the v10 commits / commit_modifies_file tables exist on construction.
    return GraphStore(tmp_path / "graph.db")


def test_add_commit_node_persists(store: GraphStore) -> None:
    store.add_commit_node(
        hash="abc1234567890",
        author="riley",
        date="2026-08-16T12:00:00Z",
        message="feat: add commit-intent",
        branch="main",
    )
    rows = store._conn.execute(
        "SELECT hash, author, date, message, branch FROM commits WHERE hash=?",
        ("abc1234567890",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "abc1234567890"
    assert rows[0][1] == "riley"
    assert rows[0][2] == "2026-08-16T12:00:00Z"
    assert rows[0][3] == "feat: add commit-intent"
    assert rows[0][4] == "main"


def test_add_commit_node_dedupes(store: GraphStore) -> None:
    store.add_commit_node(hash="h1", author="r", date="d", message="m", branch="main")
    store.add_commit_node(hash="h1", author="r2", date="d2", message="m2", branch="main")
    row = store._conn.execute("SELECT COUNT(*) FROM commits WHERE hash='h1'").fetchone()
    assert row[0] == 1  # PRIMARY KEY wins, original kept


def test_link_commit_to_file(store: GraphStore) -> None:
    store.add_commit_node(hash="c1", author="r", date="d", message="m", branch="main")
    store.link_commit_to_file("c1", "src/foo.py")
    rows = store._conn.execute(
        "SELECT file_path FROM commit_modifies_file WHERE commit_hash='c1'"
    ).fetchall()
    assert rows[0][0] == "src/foo.py"


def test_commits_for_file_reverse_query(store: GraphStore) -> None:
    store.add_commit_node(
        hash="c1", author="r", date="2026-08-15T00:00:00Z", message="m", branch="main"
    )
    store.add_commit_node(
        hash="c2", author="r", date="2026-08-16T00:00:00Z", message="m", branch="main"
    )
    store.link_commit_to_file("c1", "a.py")
    store.link_commit_to_file("c2", "a.py")
    hits = store.commits_for_file("a.py")
    assert {c.hash for c in hits} == {"c1", "c2"}
    # ORDER BY commits.date DESC — most recent commit first
    assert hits[0].hash == "c2"
    assert hits[1].hash == "c1"
    # Returned objects are CommitMetadata dataclasses
    for c in hits:
        assert isinstance(c, CommitMetadata)


def test_files_for_commit(store: GraphStore) -> None:
    store.add_commit_node(hash="c1", author="r", date="d", message="m", branch="main")
    store.link_commit_to_file("c1", "a.py")
    store.link_commit_to_file("c1", "b.py")
    files = store.files_for_commit("c1")
    assert set(files) == {"a.py", "b.py"}


def test_commit_count(store: GraphStore) -> None:
    assert store.commit_count() == 0
    store.add_commit_node(hash="c1", author="r", date="d", message="m", branch="main")
    store.add_commit_node(hash="c2", author="r", date="d", message="m", branch="main")
    assert store.commit_count() == 2
    # idempotent add does not inflate the count
    store.add_commit_node(hash="c1", author="r2", date="d2", message="m2", branch="main")
    assert store.commit_count() == 2


# ---------------------------------------------------------------------------
# Task 3 — commit_ingest parser + ingest_commits
# ---------------------------------------------------------------------------


def test_parse_git_log_basic() -> None:
    raw = (
        "abc123\triley\t2026-08-16T12:00:00+00:00\tfeat: add commit-intent\n"
        "def456\tother\t2026-08-15T10:00:00+00:00\tfix: bug\n"
    )
    rows = parse_git_log(raw)
    assert len(rows) == 2
    assert rows[0]["hash"] == "abc123"
    assert rows[0]["author"] == "riley"
    assert rows[0]["date"] == "2026-08-16T12:00:00+00:00"
    assert rows[0]["message"] == "feat: add commit-intent"
    assert rows[1]["hash"] == "def456"


def test_truncate_message_caps_at_max_chars() -> None:
    big = "x" * 5000
    out = truncate_message(big, max_chars=2000)
    assert len(out) == 2000
    # module-level default matches
    assert truncate_message(big, max_chars=MESSAGE_MAX_CHARS) == big[:MESSAGE_MAX_CHARS]


def test_truncate_message_short_unchanged() -> None:
    assert truncate_message("short", max_chars=2000) == "short"


def test_ingest_commits_inserts_into_graph(tmp_path: Path) -> None:
    # init a real git repo with one commit
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    (repo / "a.txt").write_text("hi")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=repo, check=True)

    db = tmp_path / "graph.db"
    store = GraphStore(db)

    new_count = ingest_commits(store, repo)
    assert new_count == 1
    assert store.commit_count() == 1
    # commit -> file edge is recorded (a.txt was the touched path)
    rows = store._conn.execute(
        "SELECT file_path FROM commit_modifies_file"
    ).fetchall()
    assert [r[0] for r in rows] == ["a.txt"]


def test_ingest_commits_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=repo, check=True)
    db = tmp_path / "graph.db"
    store = GraphStore(db)

    n1 = ingest_commits(store, repo)
    n2 = ingest_commits(store, repo)
    assert n1 == 1
    assert n2 == 0  # dedupe — second run no new commits
    assert store.commit_count() == 1