"""Query-side vocabulary for keyword search: synonyms, stemming, identifiers.

Search stays lexical. This module only rewrites the *query*: it never edits
pattern or framework text, so the normative layer is untouched.

Synonym table rules
-------------------
* A key is a phrase a practitioner might type. Its expansions are words the
  framework itself uses for the same control, and every expansion must occur
  in the shipped search corpus (titles, descriptions, SFRs or pattern text);
  research/mcp/tests/test_query_vocabulary.py enforces that.
* Entries come from three sources only: the external critique's examples
  (2026-11-05, section 9.3), vocabulary gaps behind misses in the development
  eval set (research/mcp/eval/ranking_eval.yaml), and widely used security
  and governance terms for controls the framework names differently.
* Do not add an entry to rescue one task in the held-out eval set
  (ranking_eval_heldout.yaml); that set exists to measure whether this table
  generalises.
* Expansion terms are weighted below the user's own words (see
  EXPANSION_WEIGHT in server.py), so they can lift a matching control into
  view without outranking a direct hit.
"""

from __future__ import annotations

import re

# (keys, expansions). Keys are matched on the lowercased raw query at a word
# boundary, with space and hyphen treated as interchangeable.
SYNONYMS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # Critique 9.3 examples
    (("kill switch", "killswitch", "emergency stop", "e-stop", "stop button"),
     ("intervention", "shutdown", "interruption")),
    (("sandbox",), ("sandboxing", "containment", "isolation")),
    (("audit trail", "audit log", "audit logging"), ("logging", "traceability")),
    (("human approval", "human sign-off", "human signoff", "manual approval",
      "human in the loop", "hitl"),
     ("confirmation", "oversight", "checkpoint")),
    # Development-set misses
    (("container", "containerise", "containerize", "containerised",
      "containerized", "seccomp", "gvisor", "firecracker", "microvm"),
     ("sandboxing", "isolation", "containment")),
    (("permission", "permissions", "rbac", "role-based", "access control"),
     ("authorization",)),
    (("psychological safety", "speak up", "raise concerns", "raising concerns",
      "whistleblower", "whistleblowing"),
     ("culture", "reporting")),
    (("near-miss", "near-misses", "near miss", "near misses", "blameless",
      "post-mortem", "postmortem"),
     ("incident", "culture", "reporting")),
    # Standard security and governance vocabulary
    (("least privilege", "least-privilege", "minimal privilege"),
     ("default-deny", "authorization", "capability")),
    (("jailbreak", "jailbreaks", "indirect injection"),
     ("injection", "instruction")),
    (("allowlist", "whitelist", "outbound", "network access"), ("egress",)),
    (("rollback", "roll back", "undo"), ("reversibility", "recovery")),
    (("hallucination", "hallucinations", "hallucinate", "hallucinates"),
     ("confabulation", "fidelity")),
    (("red team", "red teaming", "red-teaming", "pen test", "penetration test"),
     ("adversarial", "independent", "verification")),
    (("authenticate", "authentication", "login", "credential", "credentials"),
     ("authentication", "identity")),
    (("plugin", "plugins", "add-on", "supply chain"),
     ("third-party", "extensions", "integrations")),
    (("power-seeking", "power seeking", "resource acquisition"),
     ("instrumental", "power-seeking")),
    (("pii", "personal data"), ("privacy",)),
    (("observability", "telemetry"), ("monitoring",)),
)

_COMPILED: list[tuple[re.Pattern, tuple[str, ...], str]] = []
for _keys, _expansions in SYNONYMS:
    for _key in _keys:
        _pattern = r"\b" + r"[\s-]+".join(re.escape(p) for p in re.split(r"[\s-]+", _key)) + r"\b"
        _COMPILED.append((re.compile(_pattern), _expansions, _key))


def expand_query(raw: str) -> list[tuple[str, tuple[str, ...]]]:
    """Return (matched key, expansions) for every synonym key in `raw`."""
    text = raw.lower()
    out: list[tuple[str, tuple[str, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    for rx, expansions, key in _COMPILED:
        if expansions in seen:
            continue
        if rx.search(text):
            out.append((key, expansions))
            seen.add(expansions)
    return out


# Light suffix stripping so "isolate" finds "isolation" and "authenticate"
# finds "authentication". Matching is already anchored at word start and open
# at the end, so a stem only has to be a prefix of the indexed word. Words
# shorter than six letters and stems shorter than five are left alone to keep
# short terms from matching too widely.
_SUFFIXES = ("isation", "ization", "ation", "ising", "izing", "ise", "ize",
             "ing", "ed", "es", "s", "e")


def stem(term: str) -> str:
    if len(term) < 6 or not term.isalpha():
        return term
    for suffix in _SUFFIXES:
        if term.endswith(suffix) and len(term) - len(suffix) >= 5:
            return term[: -len(suffix)]
    return term


# Requirement identifiers. Display ids look like D2.1 (numbered), D2_1
# (underlined variant: printed as "D2.1" with an underline), D2 (suite root)
# and, for the inhibitor suites, G1 (root of I1) and I1.2 (child). People
# type them as d2.1, D2-1, "D2 1", G1.2 or I1.
_IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9:])([DdIiGg])\s?(\d{1,2})(?:(\s?[._-]\s?|\s)(\d{1,2}))?(?![A-Za-z0-9:_]|[._-]\d)"
)


def identifier_candidates(text: str) -> list[tuple[str, list[str]]]:
    """Return (as typed, [candidate display_ids]) for each identifier in `text`.

    Dot means the numbered requirement, underscore the underlined variant;
    a hyphen or space could mean either, so both are returned and the caller
    must keep both rather than silently choose. G and I prefixes are
    interchangeable: the catalogue labels inhibitor suite roots G1..G7 and
    their children I1.1, I1.2, and so on.
    """
    out: list[tuple[str, list[str]]] = []
    for m in _IDENTIFIER_RE.finditer(text):
        letter, suite_no, sep, child_no = m.group(1).upper(), m.group(2), m.group(3), m.group(4)
        typed = m.group(0)
        if child_no is None:
            if letter == "D":
                cands = [f"D{suite_no}"]
            else:
                cands = [f"G{suite_no}"]
            out.append((typed, cands))
            continue
        prefix = "D" if letter == "D" else "I"
        sep = (sep or " ").strip()
        if sep == ".":
            cands = [f"{prefix}{suite_no}.{child_no}"]
        elif sep == "_":
            cands = [f"{prefix}{suite_no}_{child_no}"]
        else:
            cands = [f"{prefix}{suite_no}.{child_no}", f"{prefix}{suite_no}_{child_no}"]
        out.append((typed, cands))
    return out
