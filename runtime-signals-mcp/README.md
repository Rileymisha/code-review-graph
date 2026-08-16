# runtime-signals-mcp

stdio MCP server that exposes **host runtime signals** so agents can see
what's running, what logs are saying, and what the CPU is doing.

Tools:

- `list_signals(kind=None)` — discover log files and Python processes
- `read_log(path, lines=100)` — tail a log file (200 lines / 32 KB max)
- `profile_python(pid, duration_s=5)` — py-spy dump a Python process

Generic — does NOT bind to any project root. Reads `/var/log`, `/tmp`,
`$HOME/logs` by default; cfg override via `runtime-signals-config.json`.

## Install

```bash
cd /home/riley/workspace/code-review-graph/runtime-signals-mcp
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Python ≥ 3.10; `fastmcp` ≥ 3.2.4 (already pinned by parent CRG pyproject).

## Optional: install py-spy

`profile_python` requires `py-spy` on PATH at runtime (not a Python dep):

```bash
uv pip install py-spy
# or: cargo install py-spy
```

If `py-spy` is missing, `profile_python` returns `isError=true` with a
helpful message — server itself still runs.

## Configuration (optional)

Drop a `runtime-signals-config.json` next to where the server runs:

```json
{
  "log_paths": ["/var/log", "/tmp", "$HOME/logs"],
  "process_filters": ["python", "python3"],
  "log_glob_patterns": ["*.log", "*.txt", "*.out"]
}
```

If missing, embedded defaults apply.

## Tools

### `list_signals(kind?)`

`kind`:
- `"log"` — files matching `log_paths` × `log_glob_patterns`
- `"process"` — running Python processes via `ps -eo pid,comm,rss,args`
- `None` (default) — both

Returns JSON array of:
```json
{
  "kind": "log",
  "path_or_pid": "/var/log/syslog",
  "size_bytes": 12345,
  "mtime": "2026-08-16T00:00:00+00:00",
  "cmdline": null,
  "rss_kb": null
}
```

### `read_log(path, lines=100)`

Read the last `lines` lines of `path`. Truncated to 200 lines / 32 KB
(whichever hits first). Errors with `isError=true` if:
- file not found
- not a regular file (directory / symlink-to-dir)
- permission denied

Returns:
```json
{
  "path": "/var/log/syslog",
  "truncated": false,
  "lines": [{"line": 1, "text": "..."}]
}
```

### `profile_python(pid, duration_s=5)`

Sample the Python process at `pid` for `duration_s` seconds via `py-spy dump`.

Returns JSON array of `{function, self_pct, cum_pct}` top-N entries.

Errors with `isError=true` if:
- pid invalid or not found
- `py-spy` not installed
- ptrace / permissions denied (non-zero exit from `code`)

## Testing

```bash
cd /home/riley/workspace/code-review-graph/runtime-signals-mcp
.venv/bin/pytest -v
```

End-to-end smoke:

```bash
timeout 1 .venv/bin/python -m runtime_signals_mcp   # starts, reads stdin, exits 124
```

## Registration (Claude Code / Cursor)

Add to **both** `code-review-graph/.mcp.json` and `~/.cursor/mcp.json`:

```json
"runtime-signals-mcp": {
  "type": "stdio",
  "command": "/home/riley/workspace/code-review-graph/runtime-signals-mcp/.venv/bin/python",
  "args": ["-m", "runtime_signals_mcp"],
  "cwd": "/home/riley/workspace/code-review-graph/runtime-signals-mcp"
}
```

After editing, **fully restart** the client process (not just close the
window) for the new tool to surface.
