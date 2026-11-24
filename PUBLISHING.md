# Publishing `saferagenticai-mcp` to MCP registries

Release runbook for the SaferAgenticAI MCP server. Ordered so one publish
cascades: the **Official MCP Registry** is the keystone — PulseMCP ingests it
daily and Glama ingests its `server.json`, so publishing there seeds several
directories at once.

The default transport is **stdio**. An optional Streamable HTTP transport is
available through the `[http]` extra and `MCP_TRANSPORT=http`. Registry bundle
publication and the hosted service are separate release surfaces. This runbook
does not identify or authorise the hosted deployment entry point.

---

## 0. Cut a release (do this first for any new version)

The ownership token the Official Registry needs lives in the **immutable** PyPI
description, so every registry change rides on a PyPI release.

```bash
cd research/mcp/server
bash scripts/sync-data.sh                 # bundle criteria + 239 patterns + heuristics into _data/
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
`scripts/build-mcpb.sh`, the `Dockerfile` pin, and `_FALLBACK_VERSION` in
`saferagenticai_mcp/__init__.py` together. (`__version__` itself is read from
the installed distribution metadata and is what the MCP initialize handshake
reports; `_FALLBACK_VERSION` only covers source checkouts, and
`tests/test_unit_server.py::TestPackageVersion` fails if it drifts from
`pyproject.toml`.)

> Status: **0.4.3 is published** (2026-11-24). This data refresh bundles catalogue snapshot `b813d153` and revised D3.9 and I1.2 delegation patterns. The ten-tool interface is unchanged. PyPI reports MIT and the Registry ownership token. Both uploaded files match their independently rebuilt artifacts: wheel SHA-256 `62d818c0c4762b7e54a3577f82bc33c796a6f466a65664109259dc0892826098`; sdist SHA-256 `ca7d2d281452619ca0368a0f29e1b550ddd5b067a7564e2f98ae712ed651e54d`.
> The Official MCP Registry lists **0.4.3** as latest (published 2026-11-24T02:21:18.90678Z). The hosted endpoint has served **0.4.3**, snapshot `b813d153`, since 2026-11-24T03:12:26Z; see `../plugin-review/DEPLOYMENT.md`.
>
> Previous release: **0.4.2** (2026-11-06, authorised by Nell's "commit and push everything live"; synonym expansion and identifier normalisation in search, every pattern served as `generated_draft`, tasks of 2+ characters; wheel SHA-256 `cfad4a55…`, sdist `562d6cd0…`, matching two byte-identical local builds; a clean install from PyPI loads 239 subgoals, 15 heuristics and 0 validation issues, and the wheel passed `verify-hosted.py` over loopback, 37 checks). The Official MCP Registry published it at 2026-11-06T03:08:55Z. The hosted endpoint has served 0.4.2 since 2026-11-06T03:19:09Z (see `../plugin-review/DEPLOYMENT.md`).
>
> Before it, **0.4.1** (2026-11-02: stdio exits cleanly when a client disconnects after a malformed message; subgoals keyed by permanent pattern ids; 239 patterns incl. D2.10 and 15 heuristics; wheel SHA-256 `2f32245e…`, sdist `94e992a5…`, matching two byte-identical local builds). Before it, **0.4.0** (2026-10-16: removes the `list_unreviewed` and `review_stats` tools, leaving ten; carries the payload-free diagnostics first deployed in the private 0.3.7 origin build) — `License-Expression: MIT`, no OSI classifier,
> ownership token present in the live description. The Official MCP Registry published **0.4.1** on 2026-11-02. Other directories update on their own schedules.

### 0.4.3 contents (published 2026-11-24)

- 239 subgoals with patterns, 15 operational heuristics and zero validation issues in a clean wheel install. The loopback HTTP verifier passed 37 checks across all ten tools.
- Dev: top-1 42.9%, top-3 81.0%, MRR@10 0.621 (0.615 in 0.4.2). Held-out: top-1 66.7%, top-3 79.2%, MRR@10 0.740. The dev top-3 floor remains 0.75.

### 0.4.2 contents (published 2026-11-06)

- Query vocabulary: synonym expansion built from the corpus, identifier
  normalisation (`d2.1`, `D2-1`, `"D2 1"`, `G1.2`), reported as
  `expanded_terms` / `identifier_matches`. Ranking eval, re-measured on the
  released code: dev top-3 71.4% -> 81.0%, MRR 0.561 -> 0.615; held-out (24
  tasks, written before tuning) top-1 66.7%, top-3 45.8% -> 79.2%, MRR 0.740.
  CI floor raised from 0.65 to 0.75.
- `review_status: generated_draft` on every pattern, as a machine-readable
  statement that patterns are model drafts; the library still has no
  human-review process (f41ce0cb).
- `find_patterns_for_task` accepts tasks of 2+ characters (was 5), so bare
  IDs such as `d3.2` work.

Publish order, so the package and its documentation never disagree: merge and
deploy the site first; then bump the version everywhere listed above, run
`sync-data.sh`, build, upload and verify; then update `mcp.html` (version pins,
`softwareVersion`, and the search-quality figures to the re-measured numbers)
and republish the registry entries. PyPI versions are permanent, which is why
this waits for the site.

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

It serves **239 implementation patterns** and **15 operational
heuristics** across all **16 safety suites** (9 Drivers + 7 Inhibitors) through
**10 read-only tools** — search patterns, resolve requirements, map a task to the
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

This runbook's Smithery release path uses an **MCPB stdio bundle**, built by
`scripts/build-mcpb.sh` (manifest at `mcpb/manifest.json`, launcher at
`mcpb/server/main.py`; dependencies are vendored because MCPB does no runtime
install). The optional HTTP transport exists separately. A hosted/container
release would require its own reviewed configuration and deployment authority.

The Smithery namespace is **`nell`** (not `NellInc`): the server is
`nell/saferagenticai-mcp`, listed since 2026-07-04 and re-released with 0.3.6 on
2026-09-03.

```bash
cd research/mcp/server
bash scripts/build-mcpb.sh            # → dist/saferagenticai-mcp-<version>.mcpb (vendors the PyPI release; refuses until it is published)
npx --yes @smithery/cli login
npx --yes @smithery/cli mcp publish dist/saferagenticai-mcp-<version>.mcpb -n nell/saferagenticai-mcp
```

> **Known CLI defect (4.11.x, smithery-ai/cli#787):** the bundle publish fails
> both ways — `400 "No values to set"` when the manifest declares no `tools`,
> and `"expected object, received undefined"` ×12 when it does, because the
> registry requires each tool's `inputSchema` and the MCPB manifest schema
> forbids it. Until the CLI maps them, release directly against the API the
> CLI uses (`PUT /servers/<qn>/releases`, multipart `payload` + `bundle`),
> with the real schemas extracted from `server.py`'s `TOOLS` list:
>
> ```bash
> T=$(npx --yes @smithery/cli whoami --full | grep -oE '[A-Za-z0-9_.-]{30,}' | head -1)
> # payload.json = {"type":"stdio","runtime":"python","serverCard":{"serverInfo":{"name":"saferagenticai-mcp","version":"<version>"},"tools":[{name,description,inputSchema}...]}}
> curl -X PUT https://api.smithery.ai/servers/nell/saferagenticai-mcp/releases \
>   -H "Authorization: Bearer $T" -F "payload=<payload.json" \
>   -F "bundle=@dist/saferagenticai-mcp-<version>.mcpb;filename=server.mcpb;type=application/zip"
> # → 202 {"deploymentId":…,"status":"SUCCESS"}; the authenticated
> #   GET /servers/nell/saferagenticai-mcp shows the new bundleUrl and tools
> #   at once, the public registry.smithery.ai read lags a few minutes.
> ```

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
    Read-only tools over the SaferAgenticAI safety framework — 239 implementation
    patterns and 15 operational heuristics across 16 safety suites (9 drivers +
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
- ✅ **Official MCP Registry** — published & live: `io.github.NellInc/saferagenticai-mcp v0.3.5` (v1.3-draft framework data).
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
- Short Description: `MCP server exposing the SaferAgenticAI safety framework: 239 implementation patterns + 15 operational heuristics via 10 read-only stdio tools. Python, MIT.`
- Email: `nell@ethicsnet.com`
- Post-publish: if the root-README crawl mis-describes it, **claim the listing** (verified badge + edit access) and fix the install commands — or just let the Official-Registry auto-discovery supersede it.

### mcpservers.org — <https://mcpservers.org/submit>
Web front-end for `wong2/awesome-mcp-servers`; **does not accept PRs**, submit via
the form (author-typed, so no mis-scrape):
- Name: `saferagenticai-mcp`
- Description: `Read-only MCP server exposing the Safer Agentic AI safety framework (239 patterns + 15 operational heuristics) via 10 query tools; Python stdio, install via uvx/pipx/pip.`
- Link: `https://pypi.org/project/saferagenticai-mcp/`  ← PyPI, not the repo root
- Category: `Other` (or `Development`)
- Email: `nell@ethicsnet.com`
- Optional: a one-time $39 "premium" tier fast-tracks review (not required to be listed).
