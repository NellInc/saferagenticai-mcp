# Container image for the SaferAgenticAI MCP server (stdio transport).
# Installs the published wheel from PyPI, which bundles the framework data
# under saferagenticai_mcp/_data/, so no repo checkout is needed at runtime.
# Used by the Docker MCP Catalog and to de-risk Glama's sandboxed build.
FROM python:3.12-slim

# Pin to the release matching this repo state. Bump alongside pyproject version.
RUN pip install --no-cache-dir "saferagenticai-mcp==0.3.3"

# The server speaks MCP over stdio; the console script is the entry point.
ENTRYPOINT ["saferagenticai-mcp"]
