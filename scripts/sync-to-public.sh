#!/usr/bin/env bash
# Mirror the authored MCP server (this directory) to its PUBLIC GitHub repo.
#
# The private SaferAgenticAI monorepo is the source of truth; the public repo
# (github.com/NellInc/saferagenticai-mcp) is a publish target — like PyPI — so
# MCP directories/registries can crawl it and Glama/Docker can clone it.
#
# Run AFTER scripts/sync-data.sh (so saferagenticai_mcp/_data/ is current).
# Unlike the monorepo, the public repo COMMITS _data (it is self-contained) and
# carries glama.json at its root (copied from the monorepo root).
#
# Preserves the public repo's history (clones + diffs, no force-push).
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"           # research/mcp/server
MONO_ROOT="$(cd "$SERVER_DIR/../../.." && pwd)"          # repo root
PUBLIC_REPO="https://github.com/NellInc/saferagenticai-mcp.git"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Cloning $PUBLIC_REPO"
git clone -q "$PUBLIC_REPO" "$WORK"

echo "==> Refreshing tracked files from $SERVER_DIR"
find "$WORK" -mindepth 1 -maxdepth 1 -not -name '.git' -exec rm -rf {} +
rsync -a \
  --exclude '.venv/' --exclude 'dist/' --exclude 'build/' --exclude '*.egg-info/' \
  --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.benchmarks/' \
  --exclude 'mcpb/server/lib/' --exclude '*.mcpb' --exclude '.git/' \
  "$SERVER_DIR/" "$WORK/"
# glama.json lives at the monorepo root; the public repo needs it at ITS root.
[ -f "$MONO_ROOT/glama.json" ] && cp "$MONO_ROOT/glama.json" "$WORK/glama.json"

# Public .gitignore commits _data (the monorepo's does not).
cat > "$WORK/.gitignore" <<'EOF'
# Build artefacts
dist/
build/
*.egg-info/
__pycache__/
*.pyc
.pytest_cache/
.benchmarks/
.venv/
# MCPB bundle build artefacts (vendored deps + packed bundle)
mcpb/server/lib/
*.mcpb
EOF

cd "$WORK"
git add -A
if git diff --cached --quiet; then
  echo "==> No changes to mirror."
  exit 0
fi
MONO_SHA="$(cd "$SERVER_DIR" && git rev-parse --short HEAD 2>/dev/null || echo local)"
git -c user.name="NellInc" -c user.email="nell@ethicsnet.com" \
  commit -qm "Sync from monorepo ${MONO_SHA}"
git push -q origin HEAD:main
echo "==> Mirrored $SERVER_DIR -> $PUBLIC_REPO"
