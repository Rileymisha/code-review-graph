"""stdio entry: `python -m runtime_signals_mcp`."""
from __future__ import annotations

from runtime_signals_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()  # default transport = stdio