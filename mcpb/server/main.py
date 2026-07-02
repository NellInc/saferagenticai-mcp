"""MCPB launcher for the SaferAgenticAI MCP server (stdio transport).

MCPB bundles run with no runtime `pip install`, so every dependency is vendored
into `server/lib/` by `scripts/build-mcpb.sh`. The manifest sets
`PYTHONPATH=${__dirname}/server/lib`; we also prepend it here so the bundle runs
even if a host launches this file without honoring `mcp_config.env`.
"""

import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if os.path.isdir(_LIB) and _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from saferagenticai_mcp.server import main

if __name__ == "__main__":
    main()
