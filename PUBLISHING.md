# Publishing `saferagenticai-mcp` to MCP registries

Release runbook for the SaferAgenticAI MCP server. Ordered so one publish
cascades: the **Official MCP Registry** is the keystone — PulseMCP ingests it
daily and Glama ingests its `server.json`, so publishing there seeds several
directories at once.

Transport is **stdio-only**. That is a non-issue at every registry below — none
require HTTP/SSE for a local server.

---

## 0. Cut a release (do this first for any new version)

The ownership token the Official Registry needs lives in the **immutable** PyPI
description, so every registry change rides on a PyPI release.

```bash
cd research/mcp/server
bash scripts/sync-data.sh                 # bundle criteria + 238 patterns + heuristics into _data/
rm -f dist/*.whl dist/*.tar.gz
uv build                                  # or: python3 -m build  (needs hatchling>=1.27 for PEP 639)
python3 -m twine upload dist/saferagenticai_mcp-<version>.whl dist/saferagenticai_mcp-<version>.tar.gz
```

Verify the upload carries the license + ownership token:

```bash
curl -s https://pypi.org/pypi/saferagenticai-mcp/<version>/json | python3 -c "
import sys,json; i=json.load(sys.stdin)['info']
print('license_expression:', i.get('license_expression'))
print('token present:', 'mcp-name: io.github.NellInc/saferagenticai-mcp' in (i.get('description') or ''))"
```

Bump `version` in `pyproject.toml`, `server.json`, `mcpb/manifest.json`,
`scripts/build-mcpb.sh`, and the `Dockerfile` pin together.

> Status: **0.3.3 is published** — `License-Expression: MIT`, no OSI classifier,
> ownership token present in the live description. The registry steps below are unblocked.

---

## 1. Official MCP Registry — keystone  ·  effort: low

Manifest already committed at `research/mcp/server/server.json`
(name `io.github.NellInc/saferagenticai-mcp`, PyPI package, stdio transport).
The registry does a **case-sensitive** namespace match against your GitHub login
`NellInc`, so the casing in `server.json` and the README token must stay exact.

```bash
brew install mcp-publisher            # or download from the registry GitHub releases
cd research/mcp/server
mcp-publisher login github            # device flow — authenticate as NellInc
mcp-publisher publish                 # uses ./server.json
# verify:
curl 'https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.NellInc/saferagenticai-mcp'
```

---

## 2. PulseMCP  ·  effort: none (automatic)  ·  via Official Registry

**Live-verified 2026-07-02:** PulseMCP no longer has a direct server-submission
form. Its "Submit → MCP Server" flow only states it **ingests the Official MCP
Registry daily** (processed weekly). So publishing to the Official Registry (§1)
*is* the PulseMCP submission — nothing else to do. For corrections to an existing
listing, email `hello@pulsemcp.com`. (Its /submit page also reCAPTCHA-blocks
automation browsers.)

---

## 3. mcp.so  ·  effort: low  ·  requires sign-in

**Live-verified 2026-07-02:** the /submit form **requires signing in** (Google or
GitHub) before it accepts a submission — it is not anonymous, and the signed-in
form has the full field set below. OAuth did **not** persist in an automation
browser (the GitHub callback lands on `about:blank`, no session cookie is set), so
**submit from your normal browser**, where your GitHub session already exists.

Sign in at <https://mcp.so/submit> (GitHub), then fill:

- **Type:** `MCP Server`
- **Name:** `saferagenticai-mcp`
- **URL:** `https://github.com/NellInc/saferagenticai-mcp`
- **Avatar image URL:** `https://www.saferagenticai.org/assets/figures/AI_Safety_Logo-Color.png`
- **Tags:** `ai-safety, agentic-ai, governance, safety-framework, compliance, mcp`
- **Server Config:** `{"mcpServers":{"saferagenticai":{"command":"uvx","args":["saferagenticai-mcp"]}}}`
- **Content** (markdown body):

```markdown
**SaferAgenticAI MCP** brings the Safer Agentic AI safety framework to coding
assistants over the Model Context Protocol.

It serves **238 normative implementation patterns** and **14 operational
heuristics** across all **16 safety suites** (9 Drivers + 7 Inhibitors) through
**12 read-only tools** — search patterns, resolve requirements, map a task to the
relevant safety guidance, and follow cross-references.

**Highlights**
- Read-only, no auth, no external calls — framework data is bundled in the package
- stdio transport · Python ≥3.10 · MIT licensed

**Install**

    uvx saferagenticai-mcp

(or `pipx install saferagenticai-mcp`)

**Config**

    {"mcpServers":{"saferagenticai":{"command":"uvx","args":["saferagenticai-mcp"]}}}

More: https://www.saferagenticai.org
```

---

## 4. Glama  ·  effort: low

`glama.json` (maintainer `NellInc`) is committed at the repo root, and the root
`LICENSE` satisfies Glama's one hard requirement. The subdirectory `Dockerfile`
de-risks Glama's sandbox build (a failed build hides the server from search).

- Sign in at <https://glama.ai> via GitHub OAuth (needs write/admin on the repo).
- **Add Server** with `https://github.com/NellInc/saferagenticai-mcp`.
- **Sync Server** to trigger an immediate scan.

---

## 5. Smithery — via MCPB stdio bundle  ·  effort: low–med  ·  optional

Smithery's `smithery.yaml` is for its *hosted/container* path (needs an HTTP
transport we don't have). The correct route for a stdio server is an **MCPB
bundle** — built by `scripts/build-mcpb.sh` (manifest at `mcpb/manifest.json`,
launcher at `mcpb/server/main.py`; deps are vendored because MCPB does no runtime
install).

```bash
cd research/mcp/server
bash scripts/build-mcpb.sh            # → dist/saferagenticai-mcp-<version>.mcpb (verified: builds, 238 patterns bundled, launcher runs)
npx --yes @smithery/cli login
npx --yes @smithery/cli mcp publish dist/saferagenticai-mcp-<version>.mcpb -n NellInc/saferagenticai-mcp
```

---

## 6. Docker MCP Catalog  ·  effort: medium  ·  optional

A `Dockerfile` (installs the wheel from PyPI) is committed in this directory.
Submission is a PR to [`docker/mcp-registry`](https://github.com/docker/mcp-registry)
whose `task create` wizard builds the image, verifies it lists tools, and
generates `servers/saferagenticai-mcp/server.yaml`.

**Caveat:** `task create` builds from a Dockerfile at the **repo root**, but ours
is in `research/mcp/server/`. Since the Dockerfile is PyPI-based (location-
independent), simplest options are: (a) run `task create` against a branch with
the Dockerfile copied to root, or (b) use the pre-built-image path
(`task create -- --image mcp/saferagenticai-mcp ...`).

```bash
git clone https://github.com/<you>/mcp-registry && cd mcp-registry
task create -- --category productivity https://github.com/NellInc/saferagenticai-mcp
task validate -- --name saferagenticai-mcp
task build -- --tools saferagenticai-mcp
# then open a PR using .github/PULL_REQUEST_TEMPLATE.md
```

Reference `server.yaml` (the wizard will produce its own — this is a starting point):

```yaml
name: saferagenticai-mcp
image: mcp/saferagenticai-mcp
type: server
meta:
  category: productivity          # set via --category; adjust to the closest catalog category
  tags:
    - ai-safety
    - governance
    - agentic-ai
about:
  title: Safer Agentic AI
  description: >-
    Read-only tools over the SaferAgenticAI safety framework — 238 implementation
    patterns and 14 operational heuristics across 16 safety suites (9 drivers +
    7 inhibitors). Search patterns, resolve requirements, and map tasks to safety
    guidance from a coding assistant.
  icon: https://www.google.com/s2/favicons?domain=saferagenticai.org&sz=64
source:
  project: https://github.com/NellInc/saferagenticai-mcp
  branch: main
  commit: <40-char-sha where the root Dockerfile exists>
# No config block: the server takes no secrets/env and bundles its own data.
```

---

## 7. Additional community directories  ·  effort: low  ·  optional

All accept a plain Python stdio server. The shared caveat is our monorepo: point
listings at the **PyPI page** or the `research/mcp/server` subdirectory (never the
repo root, whose README is about the website). Publishing `server.json` to the
Official Registry (§1) is the cleanest fix — **mcp.directory auto-ingests registry
entries**, yielding an accurate, namespace-verified listing.

### mcp.so — <https://mcp.so/submit> (requires Google/GitHub sign-in)
Covered in §3. Manual form; you must sign in before it accepts the submission.

### Status (2026-07-02)
- ✅ **Official MCP Registry** — published & live: `io.github.NellInc/saferagenticai-mcp v0.3.3`.
- ✅ **PulseMCP** — covered via the registry ingest (no form to submit).
- ✅ **mcp.directory** — submitted (review ≤24h; email to nell@ethicsnet.com on publish).
- ✅ **mcpservers.org** — submitted (review ≤12h).
- ⏳ **mcp.so** — submit from your own browser (OAuth won't persist in automation); full field set in §3.
- ⬜ **Glama / Smithery / Docker** — optional; steps in §4–6.

### mcp.directory — <https://mcp.directory/submit>
Auto-crawls the GitHub URL you give it (and separately auto-discovers the Official
Registry). Only the repo URL is required, but supply the PyPI name + a description
so it doesn't mis-read the root:
- GitHub Repository (required): `https://github.com/NellInc/saferagenticai-mcp`
- PyPI Package: `saferagenticai-mcp`
- Short Description: `MCP server exposing the SaferAgenticAI safety framework: 238 normative patterns + 14 operational heuristics via 12 read-only stdio tools. Python, MIT.`
- Email: `nell@ethicsnet.com`
- Post-publish: if the root-README crawl mis-describes it, **claim the listing** (verified badge + edit access) and fix the install commands — or just let the Official-Registry auto-discovery supersede it.

### mcpservers.org — <https://mcpservers.org/submit>
Web front-end for `wong2/awesome-mcp-servers`; **does not accept PRs**, submit via
the form (author-typed, so no mis-scrape):
- Name: `saferagenticai-mcp`
- Description: `Read-only MCP server exposing the Safer Agentic AI safety framework (238 patterns + 14 operational heuristics) via 12 query tools; Python stdio, install via uvx/pipx/pip.`
- Link: `https://pypi.org/project/saferagenticai-mcp/`  ← PyPI, not the repo root
- Category: `Other` (or `Development`)
- Email: `nell@ethicsnet.com`
- Optional: a one-time $39 "premium" tier fast-tracks review (not required to be listed).
