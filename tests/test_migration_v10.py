"""Tests for schema migration v10: commits + commit_modifies_file tables."""

from code_review_graph.graph import GraphStore
from code_review_graph.migrations import CURRENT_VERSION, MIGRATIONS


def test_migration_v10_creates_commits_table(tmp_path):
    db = tmp_path / "graph.db"
    store = GraphStore(db)
    # GraphStore.__init__ runs the migration framework, so tables should exist
    # immediately after construction (no separate .initialize() method exists).
    cur = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='commits'"
    )
    assert cur.fetchone() is not None
    cur = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='commit_modifies_file'"
    )
    assert cur.fetchone() is not None
    # Index from the brief
    cur = store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name='idx_commit_modifies_file_path'"
    )
    assert cur.fetchone() is not None
    # Version constants and registration
    assert CURRENT_VERSION == 10
    assert 10 in MIGRATIONS
    store.close()