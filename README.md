# SaferAgenticAI MCP Server

<!-- mcp-name: io.github.NellInc/saferagenticai-mcp -->

Serves the SaferAgenticAI framework (canonical criteria + Implementation Patterns layer) to coding assistants via the Model Context Protocol.

## Available in

Published to the canonical MCP catalogues — install from a registry-aware client or the CLI below:

- **[PyPI](https://pypi.org/project/saferagenticai-mcp/)** — `saferagenticai-mcp`
- **[Official MCP Registry](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.NellInc/saferagenticai-mcp)** — `io.github.NellInc/saferagenticai-mcp`

Also rolling out across the wider MCP ecosystem: [mcp.directory](https://mcp.directory), [mcpservers.org](https://mcpservers.org), [PulseMCP](https://www.pulsemcp.com) (via the registry ingest), and [mcp.so](https://mcp.so).

## Install

Pick the path that matches your setup.

### Option 1 — `uvx` (fastest, no manual venv)

If you have [uv](https://github.com/astral-sh/uv) installed, point your MCP
client at:

```
uvx --from git+https://github.com/NellInc/saferagenticai-mcp saferagenticai-mcp
```

uv handles isolation and caches the install. Works for single-command config
lines in `~/.claude/mcp.json`.

### Option 2 — `pipx` (isolated global install)

```bash
pipx install "git+https://github.com/NellInc/saferagenticai-mcp"
```

Exposes `saferagenticai-mcp` globally; updated with `pipx upgrade saferagenticai-mcp`.

### Option 3 — manual venv (works offline from a checkout)

Homebrew / system Python blocks direct `pip install` under PEP 668, so if
you've cloned the repo and want an editable install:

```bash
python3 -m venv research/mcp/.venv
research/mcp/.venv/bin/pip install -e research/mcp/server
```

Produces `research/mcp/.venv/bin/saferagenticai-mcp`. Pattern YAML edits in
the repo are picked up live (editable mode).

### Option 4 — from PyPI

```bash
pipx install saferagenticai-mcp
# or, with the modern uv toolchain:
uv tool install saferagenticai-mcp
# or plain pip:
pip install --user saferagenticai-mcp
```

For audit-trail reproducibility, pin the version: `pipx install saferagenticai-mcp==0.3.3`.
The package bundles `criteria-v1.json` + 238 pattern YAMLs + 4 exemplars
+ `operational_heuristics.yaml` inside `saferagenticai_mcp/_data/`, so a
wheel install works without any repo checkout. (The 0.3.0 wheel predates the
corpus extension and bundles only 214 patterns, no heuristics; 0.3.1 is the
first complete build.)

## Configure (Claude Code)

Add to `~/.claude/mcp.json` (or your IDE's MCP config). Pick the variant that
matches your install option.

### With `uvx`

```json
{
  "mcpServers": {
    "saferagenticai": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/NellInc/saferagenticai-mcp",
        "saferagenticai-mcp"
      ]
    }
  }
}
```

### With `pipx` or manual venv

```json
{
  "mcpServers": {
    "saferagenticai": {
      "command": "/absolute/path/to/saferagenticai-mcp"
    }
  }
}
```

For a manual venv checkout, the absolute path is
`<repo>/research/mcp/.venv/bin/saferagenticai-mcp`.

Restart Claude Code / your IDE after editing. The server will load on the
first tool call from your assistant.

## Tools (12 total)

| Tool | Input | Returns |
|---|---|---|
| `list_suites` | — | 16 suites with titles and subgoal counts |
| `get_requirement` | `id`, `include_pattern` | one subgoal + its Pattern layer; falls back to fuzzy candidates if no exact match |
| `list_requirements` | suite/type/content_type/confidence filters | filtered subgoal list with reliability signals |
| `search_patterns` | `query`, `limit`, `verbosity` | field-weighted ranked matches with `matched_in` and (in full mode) snippets + confidence flags. Field weights: title 10×, summary 4×, sfr 3×, description 2×, body 1× |
| `get_cross_references` | `id`, `include_inferred` | outgoing adjacencies |
| `get_reverse_references` | `id` | incoming adjacencies (who cites this pattern) |
| `resolve_id` | `query` | canonicalise a partial id, slug fragment, or display_id; always returns candidates |
| `find_patterns_for_task` | `task`, `limit`, `verbosity` | top patterns grouped by suite for a task description; defaults to compact mode for cheap triage |
| `list_unreviewed` | `limit` | patterns without `reviewed_by`, sorted low-confidence first |
| `review_stats` | — | coverage %, per-suite, per-confidence; plus validation issue count |
| `list_operational_heuristics` | `suite_id`?, `query`? | operational heuristics distilled from production agentic AI deployment, optionally filtered by suite or keyword |
| `get_operational_heuristic` | `id` | single operational heuristic by id (e.g. `OH::geoffrey-pattern`); returns full entry with principle, framework mapping, design patterns, and discovery narrative |

## Data sources

- **Canonical framework**: `assessor/src/data/criteria-v1.json` (extracted from `framework.html`)
- **Pattern layer**: `research/mcp/suites/<SUITE>/<pattern_id>.yaml` (238 files)
- **Exemplars**: `research/mcp/exemplars/*.yaml` (fallback for four anchor subgoals)
- **Operational heuristics**: `research/mcp/operational_heuristics.yaml` (14 heuristics)

At startup the server loads both and builds an in-memory index keyed by `pattern_id`. `display_id` lookups are also supported but may resolve to multiple subgoals (underlined variants).

## Smoke test (without MCP installed)

```bash
python3 -c "
from saferagenticai_mcp.framework_loader import load_framework
idx = load_framework()
print(f'{len(idx.subgoals)} subgoals, {sum(1 for s in idx.subgoals.values() if s.has_pattern)} with patterns')
"
```

## Versioning

- Canonical framework: follows `criteria-v1.json`'s `version` field.
- Pattern layer: `v1-draft` while this directory is being populated; `v1` once reviewed.
- Server: semantic versioning. Current release is **0.3.3** (full 238-pattern corpus + operational heuristics bundled; argument validation in dispatch; MIT license with bundled `LICENSE`, corrected package metadata, and MCP-registry ownership token). Pin explicitly for audit reproducibility.

## What's already built in

- **Hot reload** — server stat-walks the source tree on each tool call; edits show up without restart.
- **Load-time validation** — required fields, content_type enum, confidence enum. Invalid patterns log WARNINGs but don't fail the server.
- **`find_patterns_for_task`** — natural-language task → top patterns grouped by suite. Replaces the need for a separate embedding index at current scale.
- **Reverse xref index** — built at load, queried by `get_reverse_references`.

## Not implemented

- Auth / remote transport (stdio only).
- Embedding-based semantic search — the field-weighted keyword scoring is sufficient at 238 patterns; embeddings would be worth it at 10× this scale.
- `mark_reviewed` write tool — deliberately not added. Phase 3 review edits go through the YAML directly (editor + git diff = auditable); the MCP stays read-only.

## License

This server (the code in this directory) is licensed **MIT** — see [`LICENSE`](LICENSE).

The safety-framework *content* it serves (the patterns, canonical criteria, and operational heuristics bundled under `saferagenticai_mcp/_data/`) is part of the SaferAgenticAI framework, published under **CC-BY-4.0** at the repository root. Attribution: Nell Watson and the Agentic AI Safety Community of Practice.
