"""stdio entry: `python -m crg_smart_mcp`."""
from __future__ import annotations

from crg_smart_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
