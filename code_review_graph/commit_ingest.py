"""Ingest git commits into the graph as Commit nodes + modify-file edges.

This module is the parser + driver for the commit-intent ingest feature
backed by migration v10 (``commits`` + ``commit_modifies_file`` tables on
``GraphStore``). It reads ``git log --first-parent`` output, parses it into
per-commit dicts, and feeds each commit plus its touched files into the
graph via :class:`code_review_graph.graph.GraphStore`.

Security invariants
-------------------
* ``subprocess.run`` only; ``shell=False`` (default) and an argv list —
  no user-controlled string is ever passed to a shell.
* Repo root is consumed as a ``pathlib.Path`` (callers are responsible for
  trust, matching the existing CRG ``_validate_repo_root`` invariant).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from code_review_graph.graph import GraphStore

# Cap for commit message columns. 2000 chars is generous for a first-line
# subject while still bounding the SQLite TEXT cell and the JSON payload
# that flows back through MCP.
MESSAGE_MAX_CHARS = 2000

# `--pretty=format:` spec producing four tab-separated columns:
# full hash, author name, ISO-8601 author date, subject line.
# Subject is single-line (git's `%s` already strips the trailing LF).
GIT_LOG_FORMAT = "%H%x09%an%x09%aI%x09%s"


def truncate_message(msg: str, max_chars: int = MESSAGE_MAX_CHARS) -> str:
    """Cap a commit message at ``max_chars``; under-limit returns unchanged.

    Truncation is hard-cut (slice) and silent: the brief specifies that
    over-long messages are simply cut off, not annotated.
    """
    if len(msg) <= max_chars:
        return msg
    return msg[:max_chars]


def parse_git_log(raw: str) -> list[dict[str, str]]:
    """Parse ``git log --pretty=format:<sep-joined>`` output.

    Each line is one commit, with four tab-separated fields:
    ``hash<TAB>author<TAB>iso-date<TAB>subject``. Empty lines and lines
    that do not split into exactly four columns are skipped silently —
    ``git log`` edge cases (empty repo, binary commit, etc.) must not
    fail ingest.

    Each returned dict has keys ``hash``, ``author``, ``date``,
    ``message``; ``message`` is already passed through :func:`truncate_message`.
    """
    out: list[dict[str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4:
            # Malformed line — skip silently. Real git log output always
            # produces four columns from the format spec above, but defensive
            # parsing keeps the ingest robust against future format changes.
            continue
        h, author, date, subj = parts
        out.append(
            {
                "hash": h,
                "author": author,
                "date": date,
                "message": truncate_message(subj),
            }
        )
    return out


def _run_git_log(repo_root: Path, branch: str = "HEAD") -> str:
    """Run ``git log --first-parent`` against ``repo_root`` and return stdout.

    ``--first-parent`` prevents merge branch commits from polluting the
    graph — we want the trunk history only.

    Raises :class:`subprocess.CalledProcessError` on a non-zero git exit
    (e.g. malformed branch ref). Callers should let that propagate or
    catch it themselves.
    """
    result = subprocess.run(
        [
            "git",
            "log",
            "--first-parent",
            f"--pretty=format:{GIT_LOG_FORMAT}",
            branch,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _run_git_show_names(repo_root: Path, commit_hash: str) -> list[str]:
    """Return the list of file paths touched by ``commit_hash``.

    Uses ``git show --name-only --format=`` so the diff metadata is
    suppressed and only filenames print, one per line. Empty / blank
    lines (no files touched, e.g. an empty commit) are filtered out.
    """
    show = subprocess.run(
        ["git", "show", "--name-only", "--format=", commit_hash],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p.strip() for p in show.stdout.splitlines() if p.strip()]


def ingest_commits(
    store: GraphStore,
    repo_root: Path,
    branch: str = "HEAD",
) -> int:
    """Ingest commits reachable from ``branch`` into the graph.

    For each parsed commit:
      1. Probe ``store.commit_count()`` before inserting the node.
      2. Call ``store.add_commit_node(...)`` (idempotent).
      3. Probe ``commit_count()`` again — if it grew, this commit was new
         and ``new_commits`` is incremented. The probe avoids re-parsing
         the entire graph on each call.

    Touched files are read once per commit via ``git show --name-only`` and
    each non-empty path is linked via ``store.link_commit_to_file`` (also
    idempotent).

    Returns the number of newly-inserted commit rows.
    """
    raw = _run_git_log(repo_root, branch=branch)
    rows = parse_git_log(raw)

    new_commits = 0
    for row in rows:
        before = store.commit_count()
        store.add_commit_node(
            hash=row["hash"],
            author=row["author"],
            date=row["date"],
            message=row["message"],
            branch=branch,
        )
        if store.commit_count() > before:
            new_commits += 1

        for path in _run_git_show_names(repo_root, row["hash"]):
            store.link_commit_to_file(row["hash"], path)

    return new_commits