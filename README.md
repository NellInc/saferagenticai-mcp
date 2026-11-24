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

uv handles isolation and caches the install, so the client can start the
server with a single command (see Configure below).

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

For audit-trail reproducibility, pin the version: `pipx install saferagenticai-mcp==0.4.3`.
The package bundles `criteria-v1.json` + 239 pattern YAMLs + 4 exemplars
+ `operational_heuristics.yaml` inside `saferagenticai_mcp/_data/`, so a
wheel install works without any repo checkout. (The 0.3.0 wheel predates the
corpus extension and bundles only 214 patterns, no heuristics; 0.3.1 is the
first complete build.)

## Configure (Claude Code)

Use the Claude Code CLI. Tested with Claude Code 2.1.318 on 2026-11-06
against 0.4.2 on the PATH (installed with pip) and through uvx:

```bash
claude mcp add --scope user saferagenticai -- saferagenticai-mcp
# Added stdio MCP server saferagenticai with command: saferagenticai-mcp  to user config
# File modified: /Users/you/.claude.json

claude mcp list
# saferagenticai: saferagenticai-mcp  - ✔ Connected
```

Other install routes use the same form:

```bash
claude mcp add --scope user saferagenticai -- uvx saferagenticai-mcp==0.4.3
claude mcp add --scope user saferagenticai -- /absolute/path/to/research/mcp/.venv/bin/saferagenticai-mcp
claude mcp add --transport http --scope user saferagenticai https://mcp.saferagenticai.org/mcp
```

Scopes: `local` (the default; this project only) and `user` (all your
projects) are stored in `~/.claude.json`; `project` is stored in `.mcp.json`
at the project root and shows `⏸ Pending approval` in `claude mcp list` until
approved in an interactive `claude` session. A project `.mcp.json` written by
`claude mcp add --scope project saferagenticai -- uvx saferagenticai-mcp==0.4.3`:

```json
{
  "mcpServers": {
    "saferagenticai": {
      "type": "stdio",
      "command": "uvx",
      "args": ["saferagenticai-mcp==0.4.3"],
      "env": {}
    }
  }
}
```

Cursor reads the same `mcpServers` body from `~/.cursor/mcp.json` (all
projects) or `.cursor/mcp.json` (one project).

## Tools (10 total)

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
| `list_operational_heuristics` | `suite_id`?, `query`? | operational heuristics distilled from production agentic AI deployment, optionally filtered by suite or keyword |
| `get_operational_heuristic` | `id` | single operational heuristic by id (e.g. `OH::geoffrey-pattern`); returns full entry with principle, framework mapping, design patterns, and discovery narrative |

## Data sources

- **Normative framework**: `framework/catalog/`, loaded through the generated `assessor/src/data/criteria-v1.json` projection
- **Pattern layer**: `research/mcp/suites/<SUITE>/<pattern_id>.yaml` (239 files)
- **Exemplars**: `research/mcp/exemplars/*.yaml` (fallback for four anchor subgoals)
- **Operational heuristics**: `research/mcp/operational_heuristics.yaml` (15 heuristics)

At startup the server loads both and builds an in-memory index keyed by `pattern_id`. `display_id` lookups are also supported but may resolve to multiple subgoals (underlined variants).

## Smoke test (without an MCP client)

The executable has no version or health-check flag, and pipx installs
it into its own virtual environment, so a plain `python3` cannot import it.
Use the environment the package lives in:

```bash
pipx runpip saferagenticai-mcp show saferagenticai-mcp   # Version: 0.4.3

"$(pipx environment --value PIPX_LOCAL_VENVS)/saferagenticai-mcp/bin/python" -c "
from saferagenticai_mcp.framework_loader import load_framework
idx = load_framework()
print(f'{len(idx.subgoals)} subgoals, {sum(1 for s in idx.subgoals.values() if s.has_pattern)} with patterns')
"
# 239 subgoals, 239 with patterns

# with uv instead of pipx:
uvx --from saferagenticai-mcp==0.4.3 python -c "import saferagenticai_mcp; print(saferagenticai_mcp.__version__)"
```

## Versioning

- Canonical framework: follows `criteria-v1.json`'s `version` field.
- Pattern layer: `v1-draft`.
- **0.4.3** bundles framework `1.3-draft`, catalogue snapshot `b813d153`, 239 patterns and 15 operational heuristics. It refreshes D3.9 and I1.2 for task-bound delegation and keeps the ten-tool interface.
- For comparison with the previous catalogue snapshot (`c9bf29f5`), pin **0.4.2**: `pipx install saferagenticai-mcp==0.4.2`.
- 0.4.2 expands common phrasings to the framework's own terms and normalises identifiers (`d3.9`, `D3-9`, `G3.9`), reporting both as `expanded_terms` and `identifier_matches`; accepts tasks of two or more characters; and serves every pattern with `review_status: generated_draft`, since the library has no human-review process. Held-out search: top-3 45.8% → 79.2%.
- 0.4.1 exits cleanly when a stdio client disconnects after a malformed message, keys subgoals by their permanent pattern ids, and bundles the 239-pattern catalog (including D2.10) and 15 operational heuristics.
- 0.4.0 removes the `list_unreviewed` and `review_stats` tools and the `needs_human_review` and `reviewed_by` pattern fields. It keeps the payload-free executable diagnostics added in the private 0.3.7 origin build. The hosted origin's current release and rollback target are recorded in `../plugin-review/DEPLOYMENT.md`.

## What's already built in

- **Hot reload** — server stat-walks the source tree on each tool call; edits show up without restart.
- **Load-time validation** — required fields, content_type enum, confidence enum. Invalid patterns log WARNINGs but don't fail the server.
- **`find_patterns_for_task`** — natural-language task → top patterns grouped by suite. Replaces the need for a separate embedding index at current scale.
- **Reverse xref index** — built at load, queried by `get_reverse_references`.

## Transport

The default transport is stdio. Streamable HTTP is available with the `[http]`
extra and `MCP_TRANSPORT=http`. It binds to loopback by default and expects an
external HTTPS reverse proxy. The public endpoint is
`https://mcp.saferagenticai.org/mcp`; its deployment and catalog must be verified
separately from a local installation.

## Not implemented

- Server-side authentication for the public read-only tools.
- Embedding-based semantic search — the field-weighted keyword scoring is sufficient at 239 patterns; embeddings would be worth it at 10× this scale.

The broader agent-native architecture proposes composite orientation, context-pack,
workspace, planning, action, and verification operations. They are explicitly not
part of the current `0.4.3` interface. See
[`../../architecture/README.md`](../../architecture/README.md) for the target and
compatibility plan.

The authoritative catalog maps current MCP identifiers and slugs to permanent
requirement IDs. Server `0.4.3` exposes ten tools, loads the
generated packaged snapshot, validates `saai.catalog.v1`, and reports the shared
snapshot hash.

## License

This server (the code in this directory) is licensed **MIT** — see [`LICENSE`](LICENSE).

The safety-framework *content* it serves (the patterns, canonical criteria, and operational heuristics bundled under `saferagenticai_mcp/_data/`) is part of the SaferAgenticAI framework, published under **CC-BY-4.0** (`LICENSE-CONTENT` at the repository root; `LICENSING.md` there sets out what each licence covers). Attribution: Nell Watson and the Agentic AI Safety Community of Practice.
