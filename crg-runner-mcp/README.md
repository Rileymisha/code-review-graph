# runner-mcp

stdio MCP server that exposes `run_command` and `list_targets` for
[code-review-graph](../). Lets Claude Code (and any MCP client) drive
the project's test / lint / format / type-check / build pipeline
directly.

## Install

```bash
cd /home/riley/workspace/code-review-graph/runner-mcp
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Requires Python ≥ 3.10 and `fastmcp` ≥ 3.2.4 (already pinned in
`pyproject.toml`).

## Configuration

Place a `runner-config.json` in your project root:

```json
{
  "targets": {
    "test":  { "description": "Run pytest", "cmd": "pytest -q" },
    "lint":  { "description": "Ruff",       "cmd": "ruff check ." }
  }
}
```

`cmd` is passed verbatim to `bash -lc`. Use absolute or relative paths
as you would in a shell.

## Required environment

| Var | Purpose |
|---|---|
| `CRG_PROJECT_ROOT` | Absolute path that contains `runner-config.json`. |

`PYTHONPATH` should also include `runner-mcp/src` so the
`runner_mcp` package resolves; this is set automatically by
`.mcp.json` at the repo root.

## Tools

### `list_targets()`

Returns:

```json
{
  "project_root": "/abs/path",
  "config_file":   "/abs/path/runner-config.json",
  "targets": [
    { "name": "test",  "description": "Run pytest", "cmd": "pytest -q" }
  ]
}
```

Errors with `isError=true` if `CRG_PROJECT_ROOT` is unset or the
config is missing / malformed.

### `run_command(cmd, cwd?, timeout_s?)`

Runs `cmd` via `bash -lc`. Default `cwd` is `$CRG_PROJECT_ROOT`;
default `timeout_s` is 120.

Success response (exit_code == 0):

```json
{
  "exit_code":   0,
  "duration_ms": 1234,
  "stdout":      "...",
  "stderr":      "...",
  "log_file":    "/tmp/runner-mcp/<uuid>.log" | null,
  "truncated":   false
}
```

Failures (non-zero exit / timeout / startup failure) come back with
`isError=true` and a single text content block describing the cause.

## Truncation

Stdout and stderr are each capped at 200 lines **or** 32 KB,
whichever hits first. When truncation occurs, the **full** output is
written to `/tmp/runner-mcp/<uuid>.log`; `truncated` and `log_file`
in the response point at it. Logs older than 7 days are reaped at
server startup.

## Testing

```bash
cd /home/riley/workspace/code-review-graph/runner-mcp
.venv/bin/pytest tests/ -v
```

End-to-end smoke (no `mcp inspector` required):

```bash
cd /home/riley/workspace/code-review-graph/runner-mcp
CRG_PROJECT_ROOT=/home/riley/workspace/code-review-graph \
PYTHONPATH=/home/riley/workspace/code-review-graph/runner-mcp/src \
  .venv/bin/python scripts/smoke.py
```

The script uses `fastmcp.Client` in-process to call `list_targets`
and `run_command` and asserts on exit codes / `isError` flags.

## Registration

`.mcp.json` at the parent repo root registers this server with the
venv-managed Python interpreter and the `CRG_PROJECT_ROOT` env var
already wired up. After pulling these changes, restart Claude Code
to pick up the new tools (`mcp__runner_mcp__list_targets` and
`mcp__runner_mcp__run_command`).
