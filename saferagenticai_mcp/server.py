"""SaferAgenticAI MCP server — stdio transport, twelve tools.

Tools:
    find_patterns_for_task(task)          -> cross-layer search (normative + heuristics)
    search_patterns(query)               -> field-weighted keyword search over framework
    get_requirement(id)                  -> one subgoal + pattern by pattern_id or display_id
    list_operational_heuristics(...)     -> list/filter operational heuristics
    get_operational_heuristic(id)        -> single operational heuristic by id
    list_suites                          -> inventory of all 16 suites
    list_requirements(...)               -> filtered subgoal list (suite, content_type, etc.)
    resolve_id(query)                    -> fuzzy id resolution to canonical pattern_id(s)
    get_cross_references(id)             -> outgoing adjacencies (explicit + inferred)
    get_reverse_references(id)           -> incoming references (who cites this pattern)
    list_unreviewed(...)                 -> unreviewed patterns for Phase 3 review
    review_stats                         -> coverage stats (reviewed %, per-suite, per-confidence)

Run: `saferagenticai-mcp` after `pip install -e .` in the server directory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

log = logging.getLogger("saferagenticai.server")
log.addHandler(logging.NullHandler())

from .framework_loader import (
    FrameworkIndex,
    HeuristicsIndex,
    OperationalHeuristic,
    Subgoal,
    heuristic_to_dict,
    load_framework,
    load_heuristics,
    newer_heuristics_exist,
    newer_source_exists,
    subgoal_to_dict,
)

_index: FrameworkIndex | None = None


def _get_index() -> FrameworkIndex:
    """Return the cached framework index, hot-reloading if any source file changed.

    Cheap: stat-walk the suites/ and exemplars/ dirs (~230 files) each call.
    For an interactive Phase-3 review workflow this is what you want: edit
    a pattern, call the MCP, see updated answer — no restart.
    """
    global _index
    if _index is None:
        _index = load_framework()
    elif newer_source_exists(_index):
        _index = load_framework()
    return _index


_heuristics: HeuristicsIndex | None = None


def _get_heuristics() -> HeuristicsIndex:
    """Return the cached heuristics index, hot-reloading if the source changed."""
    global _heuristics
    if _heuristics is None:
        _heuristics = load_heuristics()
    elif newer_heuristics_exist(_heuristics):
        _heuristics = load_heuristics()
    return _heuristics


# ---------------------------------------------------------------------------
# Tool handlers — pure Python, no MCP types.
# ---------------------------------------------------------------------------


def _tool_list_suites(idx: FrameworkIndex) -> dict:
    return {
        "framework_version": idx.version,
        "suite_count": len(idx.suites),
        "suites": sorted(idx.suites.values(), key=lambda s: s["id"]),
        "note": (
            "Drivers (D1-D9) describe properties a safe agentic AI should have. "
            "Inhibitors (I1-I7) describe harms to prevent or detect. "
            "Each suite contains multiple subgoals, each with SFRs and evidence requirements."
        ),
    }


def _clamp_limit(value, default: int, maximum: int, minimum: int = 1) -> int:
    """Coerce and clamp a caller-supplied `limit` into [minimum, maximum].

    The low-level MCP Server does not enforce a tool's inputSchema, so a
    non-conforming client can send a negative, zero, float, or non-numeric
    limit. A negative limit silently drops the last N results and a zero
    limit returns an empty page; both are surprising. Coerce defensively and
    fall back to `default` on anything unparseable.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(n, maximum))


def _fuzzy_candidates(idx: FrameworkIndex, id_str: str, limit: int = 5) -> list:
    """Return up to `limit` best-matching subgoals for a malformed/partial id.

    Strategy: score each subgoal by how well its pattern_id, display_id, or
    title matches `id_str`. Cheap substring + prefix heuristics — no ML.
    """
    needle = id_str.lower().strip()
    if not needle:
        return []

    scored: list[tuple[int, Subgoal]] = []
    for s in idx.subgoals.values():
        score = 0
        pid_low = s.pattern_id.lower()
        disp_low = s.display_id.lower()
        title_low = s.title.lower()

        if needle == pid_low or needle == disp_low:
            score += 1000
        if pid_low.startswith(needle) or disp_low.startswith(needle):
            score += 100
        if needle in pid_low:
            score += 50
        # Slug-only match: e.g. 'logging-of-internal-goals-activities-and'
        pid_slug = pid_low.split("::")[-1] if "::" in pid_low else pid_low
        if needle in pid_slug or pid_slug.startswith(needle[:30]):
            score += 40
        # Title-substring match
        if needle in title_low:
            score += 30
        # Partial-word overlap in title
        needle_words = {w for w in re.split(r"\W+", needle) if len(w) > 2}
        title_words = {w for w in re.split(r"\W+", title_low) if len(w) > 2}
        score += 5 * len(needle_words & title_words)

        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda t: -t[0])
    return scored[:limit]


def _tool_get_requirement(idx: FrameworkIndex, id_str: str, include_pattern: bool) -> dict:
    matches = idx.resolve_all(id_str)
    if matches:
        if len(matches) == 1:
            return {"match_count": 1, "subgoal": subgoal_to_dict(matches[0], include_pattern)}
        return {
            "match_count": len(matches),
            "note": (
                f"'{id_str}' matched {len(matches)} subgoals (display_id collision). "
                "Use pattern_id for an unambiguous lookup."
            ),
            "subgoals": [subgoal_to_dict(s, include_pattern) for s in matches],
        }

    # No exact match — fuzzy fall-through so the caller never has to guess.
    candidates = _fuzzy_candidates(idx, id_str, limit=5)
    if not candidates:
        return {
            "error": f"no subgoal found for '{id_str}'",
            "hint": "Call resolve_id with a keyword, or search_patterns.",
        }
    return {
        "match_count": 0,
        "note": (
            f"no exact match for '{id_str}'. Closest candidates shown — "
            "re-call with a pattern_id from this list."
        ),
        "candidates": [
            {
                "pattern_id": s.pattern_id,
                "display_id": s.display_id,
                "title": s.title,
                "suite_id": s.suite_id,
                "score": score,
            }
            for score, s in candidates
        ],
    }


def _meets_confidence(pattern_conf: str | None, min_conf: str) -> bool:
    order = {"low": 0, "medium": 1, "high": 2}
    if min_conf not in order:
        return True
    if pattern_conf not in order:
        return False
    return order[pattern_conf] >= order[min_conf]


def _tool_list_requirements(idx: FrameworkIndex, **filters) -> dict:
    results: list[Subgoal] = list(idx.subgoals.values())

    if suite := filters.get("suite_id"):
        results = [s for s in results if s.suite_id == suite]
    if stype := filters.get("suite_type"):
        results = [s for s in results if s.suite_type == stype]
    if ctype := filters.get("content_type"):
        results = [s for s in results if s.content_type == ctype]
    if min_conf := filters.get("min_confidence"):
        results = [s for s in results if _meets_confidence(s.confidence, min_conf)]
    if filters.get("missing_pattern_only"):
        results = [s for s in results if not s.has_pattern]

    # Cap response size to prevent unbounded payloads. Clamp both ends and
    # coerce defensively: schema validation is client/SDK-dependent, so a
    # negative or non-numeric limit must not bypass the cap.
    try:
        limit = int(filters.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))
    total_count = len(results)
    results = results[:limit]

    include_pattern = bool(filters.get("include_pattern", False))
    return {
        "match_count": total_count,
        "returned": len(results),
        "truncated": total_count > limit,
        "filters": {k: v for k, v in filters.items() if v is not None},
        "subgoals": [subgoal_to_dict(s, include_pattern) for s in results],
    }


def _count_occurrences(haystack: str, needles: list[str]) -> tuple[int, str]:
    """Return (count_of_distinct_matching_terms, best snippet) for lowercase substring matches."""
    h = haystack.lower()
    count = 0
    snippet = ""
    for n in needles:
        if n in h:
            count += 1
            if not snippet:
                i = h.find(n)
                start = max(0, i - 60)
                end = min(len(haystack), i + 120)
                snippet = haystack[start:end].strip()
    return count, snippet


FIELD_WEIGHTS = {
    "title": 10,
    "summary": 4,
    "sfr": 3,
    "description": 2,
    "body": 1,
}


def _pattern_text(pattern: dict) -> str:
    """Recursively collect all string values from a pattern dict for search."""
    parts: list[str] = []
    for v in pattern.values():
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.extend(val for val in item.values() if isinstance(val, str))
    return " ".join(parts)


def _tool_search_patterns(
    idx: FrameworkIndex, query: str, limit: int, verbosity: str = "full"
) -> dict:
    """Field-weighted keyword search.

    Weights: title 10x, summary 4x, SFR text 3x, description 2x, pattern body 1x.
    Returns the snippet from the highest-weighted field that matched,
    so callers see *why* the match was ranked high.

    `verbosity`:
        - "compact": id, display_id, suite_id, title, score, matched_in
          (no snippet, no confidence flags). ~70% smaller; use for triage.
        - "full" (default): adds snippet, confidence, needs_human_review.
    """
    limit = _clamp_limit(limit, default=10, maximum=50)
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    if not terms:
        return {"error": "empty query"}

    scored: list[tuple[int, Subgoal, str, str]] = []
    for s in idx.subgoals.values():
        total = 0
        best_snippet = ""
        best_field = ""

        # Title: heavy weight
        c, snip = _count_occurrences(s.title, terms)
        if c:
            total += c * FIELD_WEIGHTS["title"]
            if snip and not best_snippet:
                best_snippet = snip
                best_field = "title"

        # Summary (if patterned): weight 4
        if s.pattern:
            summary = str(s.pattern.get("summary", ""))
            c, snip = _count_occurrences(summary, terms)
            if c:
                total += c * FIELD_WEIGHTS["summary"]
                if snip and best_field in ("", "body"):
                    best_snippet = snip
                    best_field = "summary"

        # SFR text: weight 3
        for sfr in s.sfrs:
            txt = sfr.get("text", "")
            c, snip = _count_occurrences(txt, terms)
            if c:
                total += c * FIELD_WEIGHTS["sfr"]
                if snip and best_field in ("", "body", "description"):
                    best_snippet = snip
                    best_field = "sfr"

        # Description: weight 2
        c, snip = _count_occurrences(s.description, terms)
        if c:
            total += c * FIELD_WEIGHTS["description"]
            if snip and best_field in ("", "body"):
                best_snippet = snip
                best_field = "description"

        # Pattern body (everything else): weight 1
        if s.pattern:
            body = _pattern_text(s.pattern)
            c, snip = _count_occurrences(body, terms)
            if c:
                total += c * FIELD_WEIGHTS["body"]
                if snip and not best_snippet:
                    best_snippet = snip
                    best_field = "body"

        if total > 0:
            scored.append((total, s, best_snippet, best_field))

    scored.sort(key=lambda t: -t[0])
    top = scored[:limit]
    compact = verbosity == "compact"
    results = []
    for score, s, snippet, field in top:
        row = {
            "pattern_id": s.pattern_id,
            "display_id": s.display_id,
            "suite_id": s.suite_id,
            "title": s.title,
            "score": score,
            "matched_in": field,
        }
        if not compact:
            row["snippet"] = snippet
            row["confidence"] = s.pattern.get("confidence") if s.pattern else None
            row["needs_human_review"] = (
                s.pattern.get("needs_human_review") if s.pattern else None
            )
        results.append(row)
    out = {
        "query": query,
        "total_matches": len(scored),
        "returned": len(top),
        "results": results,
    }
    if compact:
        out["verbosity"] = "compact"
        out["next_step_hint"] = (
            "Pick a pattern_id and call get_requirement(id) for full pattern body, "
            "or re-call with verbosity='full' for snippets and confidence flags."
        )
    return out


def _tool_resolve_id(idx: FrameworkIndex, query: str, limit: int = 5) -> dict:
    """Resolve a loose reference (partial id, display_id, slug fragment, title) to candidates."""
    limit = _clamp_limit(limit, default=5, maximum=20)
    # Exact resolvers first
    exact = idx.resolve_all(query)
    if exact:
        return {
            "query": query,
            "resolved": True,
            "match_count": len(exact),
            "candidates": [
                {
                    "pattern_id": s.pattern_id,
                    "display_id": s.display_id,
                    "suite_id": s.suite_id,
                    "title": s.title,
                    "score": 1000,
                }
                for s in exact
            ],
        }
    # Fuzzy fallback
    scored = _fuzzy_candidates(idx, query, limit=limit)
    return {
        "query": query,
        "resolved": False,
        "match_count": len(scored),
        "candidates": [
            {
                "pattern_id": s.pattern_id,
                "display_id": s.display_id,
                "suite_id": s.suite_id,
                "title": s.title,
                "score": score,
            }
            for score, s in scored
        ],
    }


_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "for", "in", "on", "at",
    "by", "with", "that", "this", "is", "are", "was", "were", "be", "been",
    "being", "it", "its", "i", "we", "our", "my", "you", "your", "how", "what",
    "when", "where", "why", "do", "does", "did", "can", "should", "would",
    "will",
}


def _tool_find_patterns_for_task(
    idx: FrameworkIndex, task: str, limit: int = 8, verbosity: str = "compact"
) -> dict:
    """Given a natural-language task description, return the most relevant patterns.

    Thin wrapper: extracts content words, runs field-weighted search, then
    groups results by suite so the caller sees which concerns a task spans.

    `verbosity` defaults to "compact" here: callers typically use this tool
    for triage, then drill into a chosen pattern_id with get_requirement().
    Pass "full" to inline snippets and confidence flags.
    """
    limit = _clamp_limit(limit, default=8, maximum=25)
    words = [w for w in re.split(r"\W+", task.lower()) if len(w) > 2 and w not in _STOPWORDS]
    if not words:
        return {"error": "task description too short after stop-word removal"}
    query = " ".join(words)

    search = _tool_search_patterns(idx, query, limit=limit, verbosity=verbosity)
    if "error" in search:
        return search

    # Group by suite, with suite title for context
    by_suite: dict[str, list] = {}
    for hit in search["results"]:
        by_suite.setdefault(hit["suite_id"], []).append(hit)

    suites_touched = []
    for suite_id in sorted(by_suite.keys()):
        suite_meta = idx.suites.get(suite_id, {})
        suites_touched.append(
            {
                "suite_id": suite_id,
                "suite_title": suite_meta.get("title", ""),
                "suite_type": suite_meta.get("type", ""),
                "patterns": by_suite[suite_id],
            }
        )

    # Cross-layer: also search operational heuristics for relevant principles.
    hidx = _get_heuristics()
    relevant_heuristics = []
    for h in hidx.heuristics.values():
        text = f"{h.title} {h.principle} {h.discovery_narrative}".lower()
        score = sum(text.count(w) for w in words)
        mapped_suites = {m["suite_id"] for m in h.framework_mapping if "suite_id" in m}
        touched_suite_ids = {s["suite_id"] for s in suites_touched}
        if mapped_suites & touched_suite_ids:
            score += 3
        if score > 0:
            relevant_heuristics.append({
                "id": h.id,
                "title": h.title,
                "principle": h.principle.strip(),
                "mapped_suites": sorted(mapped_suites),
                "score": score,
            })
    relevant_heuristics.sort(key=lambda x: -x["score"])

    return {
        "task": task,
        "keywords_used": words,
        "total_matches": search["total_matches"],
        "suites_touched": suites_touched,
        "flat_top": search["results"],
        "operational_heuristics": relevant_heuristics[:5],
        "next_step_hint": (
            "For each pattern_id above, call get_requirement(id, include_pattern=true) "
            "to see its named design patterns, anti-patterns, and SFR anchors. "
            "For operational heuristics, call get_operational_heuristic(id) for the full entry."
        ),
    }


def _tool_get_cross_references(
    idx: FrameworkIndex, id_str: str, include_inferred: bool
) -> dict:
    matches = idx.resolve_all(id_str)
    if not matches:
        return {"error": f"no subgoal found for '{id_str}'"}
    if len(matches) > 1:
        return {
            "error": f"'{id_str}' is ambiguous ({len(matches)} matches). Use a pattern_id.",
            "candidates": [m.pattern_id for m in matches],
        }
    s = matches[0]

    explicit: list[str] = []
    if s.pattern:
        refs = s.pattern.get("cross_references") or []
        if isinstance(refs, str):
            refs = [refs]
        explicit = [r for r in refs if r in idx.subgoals]

    inferred: list[dict] = []
    if include_inferred:
        # Suite neighbours (same suite, not the same subgoal)
        for pid in idx.by_suite.get(s.suite_id, []):
            if pid == s.pattern_id:
                continue
            if pid in explicit:
                continue
            inferred.append(
                {
                    "pattern_id": pid,
                    "reason": "same suite",
                    "display_id": idx.subgoals[pid].display_id,
                    "title": idx.subgoals[pid].title,
                }
            )

    return {
        "of": {
            "pattern_id": s.pattern_id,
            "display_id": s.display_id,
            "title": s.title,
        },
        "explicit_cross_references": [
            {
                "pattern_id": pid,
                "display_id": idx.subgoals[pid].display_id,
                "title": idx.subgoals[pid].title,
                "suite_id": idx.subgoals[pid].suite_id,
            }
            for pid in explicit
        ],
        "inferred_adjacent": inferred,
        "review_notes": s.pattern.get("review_notes") if s.pattern else None,
    }


def _tool_list_unreviewed(idx: FrameworkIndex, limit: int | None = None) -> dict:
    """Return patterns that have no `reviewed_by` field yet.

    Intended for Phase 3: Nell walks through unreviewed patterns.
    Sort order: low confidence first, then `needs_human_review: true`, then alpha.
    """
    unreviewed: list[Subgoal] = []
    for s in idx.subgoals.values():
        if not s.pattern:
            continue
        if s.pattern.get("reviewed_by"):
            continue
        unreviewed.append(s)

    def sort_key(s: Subgoal):
        p = s.pattern or {}
        conf = p.get("confidence", "medium")
        conf_rank = {"low": 0, "medium": 1, "high": 2}.get(conf, 1)
        needs = 0 if p.get("needs_human_review") else 1
        return (conf_rank, needs, s.pattern_id)

    unreviewed.sort(key=sort_key)
    if limit is not None:
        # None = return all; any supplied value is coerced/clamped to [1, 250].
        unreviewed = unreviewed[: _clamp_limit(limit, default=250, maximum=250)]

    total = sum(
        1 for s in idx.subgoals.values() if s.pattern and not s.pattern.get("reviewed_by")
    )
    return {
        "total_unreviewed": total,
        "returned": len(unreviewed),
        "subgoals": [
            {
                "pattern_id": s.pattern_id,
                "display_id": s.display_id,
                "suite_id": s.suite_id,
                "title": s.title,
                "confidence": s.confidence,
                "needs_human_review": (s.pattern or {}).get("needs_human_review", False),
                "content_type": s.content_type,
            }
            for s in unreviewed
        ],
        "next_step_hint": (
            "After reviewing a pattern, add `reviewed_by: <your name>` and "
            "`reviewed_on: <ISO date>` to its YAML. The server hot-reloads on "
            "file change."
        ),
    }


def _tool_review_stats(idx: FrameworkIndex) -> dict:
    """Return coverage stats: reviewed vs unreviewed, per suite, per confidence."""
    total = 0
    reviewed = 0
    per_suite_total: dict[str, int] = {}
    per_suite_reviewed: dict[str, int] = {}
    per_conf_total: dict[str, int] = {}
    per_conf_reviewed: dict[str, int] = {}
    flagged_for_review = 0
    flagged_reviewed = 0

    for s in idx.subgoals.values():
        if not s.pattern:
            continue
        total += 1
        suite = s.suite_id
        conf = s.confidence or "unknown"
        per_suite_total[suite] = per_suite_total.get(suite, 0) + 1
        per_conf_total[conf] = per_conf_total.get(conf, 0) + 1
        if s.pattern.get("needs_human_review"):
            flagged_for_review += 1
        if s.pattern.get("reviewed_by"):
            reviewed += 1
            per_suite_reviewed[suite] = per_suite_reviewed.get(suite, 0) + 1
            per_conf_reviewed[conf] = per_conf_reviewed.get(conf, 0) + 1
            if s.pattern.get("needs_human_review"):
                flagged_reviewed += 1

    def pct(r: int, t: int) -> float:
        return round(100 * r / t, 1) if t else 0.0
    return {
        "total_patterns": total,
        "reviewed": reviewed,
        "unreviewed": total - reviewed,
        "percent_reviewed": pct(reviewed, total),
        "flagged_for_review": flagged_for_review,
        "flagged_and_reviewed": flagged_reviewed,
        "by_suite": {
            suite: {
                "total": per_suite_total[suite],
                "reviewed": per_suite_reviewed.get(suite, 0),
                "percent": pct(per_suite_reviewed.get(suite, 0), per_suite_total[suite]),
            }
            for suite in sorted(per_suite_total.keys())
        },
        "by_confidence": {
            c: {
                "total": per_conf_total[c],
                "reviewed": per_conf_reviewed.get(c, 0),
                "percent": pct(per_conf_reviewed.get(c, 0), per_conf_total[c]),
            }
            for c in ("low", "medium", "high")
            if c in per_conf_total
        },
        "validation_issues_at_load": len(idx.validation_issues),
        "sample_validation_issues": idx.validation_issues[:5],
    }


def _tool_get_reverse_references(idx: FrameworkIndex, id_str: str) -> dict:
    """Return patterns that reference the given pattern_id in their cross_references."""
    matches = idx.resolve_all(id_str)
    if not matches:
        return {"error": f"no subgoal found for '{id_str}'"}
    if len(matches) > 1:
        return {
            "error": f"'{id_str}' is ambiguous ({len(matches)} matches). Use a pattern_id.",
            "candidates": [m.pattern_id for m in matches],
        }
    target = matches[0]
    referrers = idx.reverse_xrefs.get(target.pattern_id, [])
    return {
        "of": {
            "pattern_id": target.pattern_id,
            "display_id": target.display_id,
            "title": target.title,
        },
        "referenced_by_count": len(referrers),
        "referenced_by": [
            {
                "pattern_id": pid,
                "display_id": idx.subgoals[pid].display_id,
                "suite_id": idx.subgoals[pid].suite_id,
                "title": idx.subgoals[pid].title,
            }
            for pid in referrers
        ],
    }


def _tool_list_operational_heuristics(hidx: HeuristicsIndex, **filters) -> dict:
    results = list(hidx.heuristics.values())

    if suite_id := filters.get("suite_id"):
        results = [
            h for h in results
            if any(m.get("suite_id") == suite_id for m in h.framework_mapping)
        ]

    if query := filters.get("query"):
        terms = [t.lower() for t in re.split(r"\W+", query) if t]

        def matches(h: OperationalHeuristic) -> bool:
            text = f"{h.title} {h.principle} {h.discovery_narrative}".lower()
            return any(t in text for t in terms)

        results = [h for h in results if matches(h)]

    return {
        "version": hidx.version,
        "layer": "operational-heuristics",
        "total": len(results),
        "note": (
            "Operational heuristics distilled from production agentic AI deployment. "
            "These complement the framework's normative patterns (in suites/) with "
            "cross-cutting principles discovered through building and operating AI agents."
        ),
        "heuristics": [heuristic_to_dict(h) for h in results],
    }


def _tool_get_operational_heuristic(hidx: HeuristicsIndex, id_str: str) -> dict:
    h = hidx.heuristics.get(id_str)
    if h:
        return {"match": True, "heuristic": heuristic_to_dict(h)}

    needle = id_str.lower()
    candidates = []
    for h in hidx.heuristics.values():
        if needle in h.id.lower() or needle in h.title.lower():
            candidates.append({"id": h.id, "title": h.title})
    if candidates:
        return {
            "match": False,
            "note": f"No exact match for '{id_str}'. Closest candidates shown.",
            "candidates": candidates[:5],
        }
    return {
        "match": False,
        "error": f"No heuristic found for '{id_str}'.",
        "hint": "Call list_operational_heuristics to see all available heuristics.",
    }


TOOL_HANDLERS = {
    "list_suites": lambda idx, args: _tool_list_suites(idx),
    "get_requirement": lambda idx, args: _tool_get_requirement(
        idx, id_str=args["id"], include_pattern=args.get("include_pattern", True)
    ),
    "list_requirements": lambda idx, args: _tool_list_requirements(idx, **args),
    "search_patterns": lambda idx, args: _tool_search_patterns(
        idx,
        query=args["query"],
        limit=args.get("limit", 10),
        verbosity=args.get("verbosity", "full"),
    ),
    "get_cross_references": lambda idx, args: _tool_get_cross_references(
        idx, id_str=args["id"], include_inferred=args.get("include_inferred", True)
    ),
    "resolve_id": lambda idx, args: _tool_resolve_id(
        idx, query=args["query"], limit=args.get("limit", 5)
    ),
    "find_patterns_for_task": lambda idx, args: _tool_find_patterns_for_task(
        idx,
        task=args["task"],
        limit=args.get("limit", 8),
        verbosity=args.get("verbosity", "compact"),
    ),
    "list_unreviewed": lambda idx, args: _tool_list_unreviewed(
        idx, limit=args.get("limit")
    ),
    "review_stats": lambda idx, args: _tool_review_stats(idx),
    "get_reverse_references": lambda idx, args: _tool_get_reverse_references(
        idx, id_str=args["id"]
    ),
    "list_operational_heuristics": lambda idx, args: _tool_list_operational_heuristics(
        _get_heuristics(), **args
    ),
    "get_operational_heuristic": lambda idx, args: _tool_get_operational_heuristic(
        _get_heuristics(), id_str=args["id"]
    ),
}


REQUIRED_ARGS = {
    "get_requirement": ("id",),
    "search_patterns": ("query",),
    "get_cross_references": ("id",),
    "resolve_id": ("query",),
    "find_patterns_for_task": ("task",),
    "get_reverse_references": ("id",),
    "get_operational_heuristic": ("id",),
}


def dispatch(name: str, arguments: dict) -> dict:
    """Call one tool. Returns the raw result dict; pure Python, no MCP types."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    args = arguments or {}
    missing = [a for a in REQUIRED_ARGS.get(name, ()) if a not in args]
    if missing:
        log.warning("Tool '%s' called without required argument '%s'", name, missing[0])
        return {"error": f"missing required argument: '{missing[0]}'"}
    try:
        # _get_index() can raise (e.g. missing/malformed bundled data — a
        # documented wheel-build failure mode); keep it inside the guard so a
        # load error returns the {"error": ...} contract instead of escaping.
        idx = _get_index()
        return handler(idx, args)
    except Exception:
        log.exception("Unhandled exception in tool '%s'", name)
        return {"error": "Internal error processing tool call"}


# ---------------------------------------------------------------------------
# MCP wiring (only imported when the mcp package is installed)
# ---------------------------------------------------------------------------


def _build_mcp_server():
    """Lazily import mcp so this module is usable for local testing without it."""
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("saferagenticai")

    TOOLS = [
        Tool(
            name="list_suites",
            description=(
                "List all 16 suites in the SaferAgenticAI framework (9 drivers + 7 inhibitors) "
                "with subgoal counts and titles. Call this first to orient."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="get_requirement",
            description=(
                "Retrieve one subgoal (framework normative content + Pattern layer guidance) "
                "by pattern_id (e.g., 'D3::idx2::sandboxing') or display_id (e.g., 'D3.2'). "
                "display_id may resolve to multiple subgoals — underlined variants share display_ids."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 500},
                    "include_pattern": {"type": "boolean", "default": True},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="list_requirements",
            description=(
                "List subgoals matching filters (suite_id, suite_type, content_type, "
                "min_confidence, missing_pattern_only). Results capped by limit (default 50, max 100)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "suite_id": {"type": "string", "maxLength": 500},
                    "suite_type": {"type": "string", "enum": ["driver", "inhibitor"]},
                    "content_type": {
                        "type": "string",
                        "enum": ["code-applicable", "governance", "process", "ecosystem"],
                    },
                    "min_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "missing_pattern_only": {"type": "boolean"},
                    "include_pattern": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="search_patterns",
            description=(
                "Field-weighted keyword search across the framework. Substring "
                "match on lowercased terms; field weights: title 10x, summary 4x, "
                "SFR text 3x, description 2x, pattern body 1x. `matched_in` "
                "reports the highest-weighted field that matched. No semantic / "
                "embedding search — known limitation, see /mcp.html. "
                "Use verbosity='compact' to drop snippets and confidence flags "
                "(~70% smaller payload) when triaging."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 2, "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                    "verbosity": {
                        "type": "string",
                        "enum": ["compact", "full"],
                        "default": "full",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_cross_references",
            description=(
                "Return outgoing adjacencies for a pattern. `explicit_cross_references` "
                "are author-asserted (each pattern's `cross_references` YAML field). "
                "`inferred_adjacent` (when include_inferred=true) currently returns "
                "*same-suite siblings only* — it does not do semantic similarity. "
                "Treat inferred entries as 'neighbours worth scanning,' not as "
                "endorsed dependencies."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 500},
                    "include_inferred": {"type": "boolean", "default": True},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="resolve_id",
            description=(
                "Resolve a loose reference (partial id, display_id, slug fragment, "
                "or title keyword) to canonical pattern_id(s). Call this when you "
                "have a rough reference and need the exact id before calling "
                "get_requirement. Always returns candidates — never 'not found'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="find_patterns_for_task",
            description=(
                "Given a natural-language task description (e.g., 'I'm building a "
                "tool-using agent that runs shell commands'), return the most relevant "
                "patterns grouped by suite. Use this as a starting point for any "
                "cross-cutting design question; then follow up with get_requirement "
                "on specific pattern_ids. Defaults to verbosity='compact' (cheap "
                "triage); pass 'full' to inline snippets and confidence flags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "minLength": 5, "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8},
                    "verbosity": {
                        "type": "string",
                        "enum": ["compact", "full"],
                        "default": "compact",
                    },
                },
                "required": ["task"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="list_unreviewed",
            description=(
                "Return patterns that have not been human-reviewed yet (no reviewed_by). "
                "Sorted low-confidence first, then needs_human_review flagged, then alpha. "
                "Use during Phase 3 review to pick the next pattern to examine."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 250},
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="review_stats",
            description=(
                "Coverage stats: total patterns, reviewed %, per-suite and per-confidence "
                "breakdown. Surfaces load-time validation issue count."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="get_reverse_references",
            description=(
                "Return patterns that reference the given pattern_id in their "
                "cross_references. Complement to get_cross_references (outgoing); "
                "this shows incoming. Use to find all consumers of a given pattern."
            ),
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string", "maxLength": 500}},
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="list_operational_heuristics",
            description=(
                "List operational heuristics distilled from production agentic AI "
                "deployment (Claude Code, Rewind). These are cross-cutting safety "
                "principles discovered through building and operating AI agents, mapped "
                "to framework suites. Optional filters: suite_id (heuristics relevant to "
                "a specific suite), query (keyword search across titles and principles). "
                "Separate from the normative pattern layer — different category of knowledge."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "suite_id": {
                        "type": "string",
                        "maxLength": 500,
                        "description": "Filter by framework suite (e.g., 'D3', 'I2')",
                    },
                    "query": {
                        "type": "string",
                        "maxLength": 500,
                        "description": "Keyword search across titles, principles, narratives",
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="get_operational_heuristic",
            description=(
                "Retrieve a single operational heuristic by id (e.g., "
                "'OH::geoffrey-pattern'). Returns the full entry: principle, framework "
                "mapping, evidence sources from production deployment, design patterns, "
                "anti-patterns, and discovery narrative."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 500},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
    ]

    @server.list_tools()
    async def list_tools():
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = dispatch(name, arguments or {})
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    return server


async def _run() -> None:
    from mcp.server.stdio import stdio_server

    server = _build_mcp_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
