# Working in `saferagenticai-mcp` — read this first

**This repository is a published mirror, not the source of truth.**

`saferagenticai-mcp` is the public, installable home of the MCP server for the
Safer Agentic AI safety framework. Its contents are **generated and mirrored**
from a private monorepo. Anything you edit *here* will be **silently overwritten**
the next time the maintainer runs the release sync (`scripts/sync-to-public.sh`).

## If you want to change something

- **Bug reports & feature requests:** open a GitHub issue here — that's the right
  place and it's watched.
- **Code / data / docs changes:** these are authored upstream in the private
  monorepo (`research/mcp/server/`) and mirrored out. A pull request against this
  repo can't be merged in the normal way (the sync would clobber it), but it is
  very welcome as a **proposal** the maintainer can apply upstream — describe the
  intent clearly and it will be carried across.

## Don't hand-edit generated content

- `saferagenticai_mcp/_data/` — the framework corpus (238 implementation patterns,
  14 operational heuristics, canonical criteria) is generated from the Safer Agentic
  AI framework upstream. Editing the YAML here changes nothing durable.

## Where it's published

- **PyPI:** `saferagenticai-mcp` — run with `uvx saferagenticai-mcp` (or `pipx` / `pip`).
- **Official MCP Registry:** `io.github.NellInc/saferagenticai-mcp` (see `server.json`).
- Rolling out across mcp.directory, mcpservers.org, PulseMCP, mcp.so, and Glama.

The registry namespace is owner-based (`io.github.NellInc/…`), so it stays valid
independent of this repo's name — the listing points at the PyPI package, not a
clone of this repo.

## Using the server

See [`README.md`](README.md) for install/config and the 12 tools (`find_patterns_for_task`,
`search_patterns`, `get_requirement`, …). More at <https://www.saferagenticai.org/mcp.html>.

---

*Maintainer: Nell Watson · Framework: <https://www.saferagenticai.org>*
