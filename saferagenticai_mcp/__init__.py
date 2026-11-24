"""SaferAgenticAI MCP server.

Exposes the two-layer framework (canonical criteria + Implementation Patterns)
to coding assistants via the Model Context Protocol.
"""

from importlib.metadata import PackageNotFoundError, version as _dist_version

# Fallback for source checkouts / bundles where the distribution metadata is
# absent. Keep in sync with pyproject.toml `version`; tests/test_unit_server.py
# asserts the two match, and PUBLISHING.md lists this file in the bump set.
_FALLBACK_VERSION = "0.4.3"

try:
    __version__ = _dist_version("saferagenticai-mcp")
except PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = _FALLBACK_VERSION

__all__ = ["__version__"]
