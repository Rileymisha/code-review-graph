"""stdio entry point: `python -m runner_mcp`."""
from __future__ import annotations

from runner_mcp.runner import LOG_DIR, cleanup_stale_logs
from runner_mcp.server import mcp

if __name__ == "__main__":
    # Reap stale artifact logs before serving (spec §"artifact 格式").
    cleanup_stale_logs(LOG_DIR)
    # Default transport is stdio.
    mcp.run()