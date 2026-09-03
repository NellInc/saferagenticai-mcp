#!/usr/bin/env bash
# Build the MCPB stdio bundle for saferagenticai-mcp (for Smithery's local /
# .mcpb distribution path). MCPB does NO runtime `pip install`, so every Python
# dependency is vendored into the bundle here.
#
# Requires: python3 (with pip) and Node/npx (for the @anthropic-ai/mcpb CLI).
# Output:   dist/saferagenticai-mcp-<version>.mcpb
#
# Usage: research/mcp/server/scripts/build-mcpb.sh
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"          # research/mcp/server
# Single source of truth for the version: pyproject.toml. The MCPB manifest
# must agree, and the bundle vendors THAT release from PyPI, so a code fix in
# this tree only reaches the bundle after the matching version is published.
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$SERVER_DIR/pyproject.toml")"
MANIFEST_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$SERVER_DIR/mcpb/manifest.json")"
if [[ -z "$VERSION" ]]; then echo "could not read version from pyproject.toml" >&2; exit 1; fi
if [[ "$VERSION" != "$MANIFEST_VERSION" ]]; then
  echo "version drift: pyproject.toml=$VERSION mcpb/manifest.json=$MANIFEST_VERSION" >&2; exit 1
fi
if ! python3 -m pip index versions saferagenticai-mcp 2>/dev/null | grep -q "$VERSION"; then
  echo "saferagenticai-mcp==$VERSION is not on PyPI yet; publish it first (the bundle vendors the PyPI release)" >&2; exit 1
fi
BUNDLE_DIR="$SERVER_DIR/mcpb"
OUT="$SERVER_DIR/dist/saferagenticai-mcp-${VERSION}.mcpb"

echo "==> Vendoring dependencies into $BUNDLE_DIR/server/lib"
rm -rf "$BUNDLE_DIR/server/lib"
python3 -m pip install --quiet --no-cache-dir --target "$BUNDLE_DIR/server/lib" "saferagenticai-mcp==${VERSION}"

echo "==> Packing MCPB bundle"
mkdir -p "$SERVER_DIR/dist"
npx --yes @anthropic-ai/mcpb pack "$BUNDLE_DIR" "$OUT"

echo "==> Built $OUT"
echo "    Publish with:  npx --yes @smithery/cli mcp publish \"$OUT\" -n NellInc/saferagenticai-mcp"
