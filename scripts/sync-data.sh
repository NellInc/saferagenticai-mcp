#!/usr/bin/env bash
# Sync runtime data (criteria + patterns + exemplars) into the package
# under saferagenticai_mcp/_data/ so `python -m build` can bundle them.
#
# Run before every release:  ./scripts/sync-data.sh
#
# Safe to run repeatedly — wipes and repopulates _data/ each time.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
server_dir="$(cd "$here/.." && pwd)"
repo_root="$(cd "$server_dir/../../.." && pwd)"

data_dir="$server_dir/saferagenticai_mcp/_data"
rm -rf "$data_dir"
mkdir -p "$data_dir"

cp "$repo_root/assessor/src/data/criteria-v1.json" "$data_dir/criteria-v1.json"
cp -R "$repo_root/research/mcp/suites"            "$data_dir/suites"
cp -R "$repo_root/research/mcp/exemplars"         "$data_dir/exemplars"
cp "$repo_root/research/mcp/operational_heuristics.yaml" "$data_dir/operational_heuristics.yaml"

n_suites=$(find "$data_dir/suites" -name '*.yaml' | wc -l | xargs)
n_exemplars=$(find "$data_dir/exemplars" -name '*.yaml' | wc -l | xargs)
echo "Synced into ${data_dir#$repo_root/}:"
echo "  criteria-v1.json"
echo "  suites/ ($n_suites YAMLs)"
echo "  exemplars/ ($n_exemplars YAMLs)"
echo "  operational_heuristics.yaml"
