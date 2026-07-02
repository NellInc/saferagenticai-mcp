"""Loads the canonical framework (criteria-v1.json) and the Pattern layer.

One in-memory index keyed by pattern_id. Each entry carries both the
normative framework content (title, description, SFRs, evidence) and
the Pattern layer enrichment (summary, design_patterns, anti_patterns,
cross_references, confidence, etc.) when available.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_YamlLoader: type = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

log = logging.getLogger("saferagenticai.framework_loader")
log.addHandler(logging.NullHandler())

# Precompiled regex patterns for _alternate_id_notation
_RE_DOT_NOTATION = re.compile(r'^([A-Z]\d+)\.(\d+)$')
_RE_UNDERSCORE_NOTATION = re.compile(r'^([A-Z]\d+)_(\d+)$')


def _resolve_data_paths() -> tuple[Path, Path, Path]:
    """Locate runtime data (criteria + patterns + exemplars).

    Two modes are supported:

      1. **Editable / development install** — invoked from a source checkout.
         Data lives at canonical repo-relative paths. Detected by walking up
         from this file to find a directory containing `research/mcp/suites`.

      2. **Non-editable install** (wheel or PyPI) — data is bundled inside the
         package at `saferagenticai_mcp/_data/...`. Detected by the presence
         of `_data/suites` next to this module.

    Editable mode takes precedence so a contributor editing pattern YAMLs in
    the repo sees their edits immediately.
    """
    here = Path(__file__).resolve()

    # Mode 1: walk up looking for a repo checkout
    for ancestor in here.parents:
        suites = ancestor / "research" / "mcp" / "suites"
        if suites.is_dir():
            return (
                ancestor / "assessor" / "src" / "data" / "criteria-v1.json",
                suites,
                ancestor / "research" / "mcp" / "exemplars",
            )

    # Mode 2: package-bundled data
    bundled = here.parent / "_data"
    if (bundled / "suites").is_dir():
        return (
            bundled / "criteria-v1.json",
            bundled / "suites",
            bundled / "exemplars",
        )

    raise FileNotFoundError(
        "SaferAgenticAI MCP could not locate pattern data in either a repo "
        "checkout or a bundled package-data directory."
    )


CRITERIA_PATH, SUITES_DIR, EXEMPLARS_DIR = _resolve_data_paths()
REPO_ROOT = CRITERIA_PATH.parents[3]  # kept for backward-compat callers

# Fields every pattern must carry. Kept in lock-step with schema.yaml.
REQUIRED_PATTERN_FIELDS = (
    "id",
    "display_id",
    "suite_id",
    "suite_title",
    "subgoal_title",
    "content_type",
    "summary",
    "normative_anchors",
    "confidence",
    "review_notes",
    "version_compat",
)
VALID_CONTENT_TYPES = {"code-applicable", "governance", "process", "ecosystem"}
VALID_CONFIDENCES = {"high", "medium", "low"}

# Content-type-specific blocks required by schema.yaml. A pattern declaring a
# content_type must carry that block's required fields.
CONTENT_TYPE_REQUIRED_BLOCKS = {
    "code-applicable": ("design_patterns", "anti_patterns"),
    "governance": ("policy_elements", "org_roles", "documentation_artifacts"),
    "process": ("process_elements", "triggers"),
    "ecosystem": ("stakeholders", "engagement_modes"),
}
NORMATIVE_ANCHOR_KEYS = (
    "sfrs_addressed",
    "evidence_addressed",
    "sfrs_not_addressed",
    "evidence_not_addressed",
)
VERSION_COMPAT_KEYS = (
    "framework_version_min",
    "framework_version_max",
    "pattern_layer_version",
)


def _alternate_id_notation(id_str: str) -> str | None:
    """Convert between dot-notation (D2.1) and underscore-notation (D2_1).

    Returns the alternate form, or None if the string doesn't match either
    pattern. This enables backward compatibility: old dot-notation IDs resolve
    even when data uses underscore-notation for underlined variants, and vice
    versa.
    """
    # D2.1 -> D2_1  (dot to underscore)
    m = _RE_DOT_NOTATION.match(id_str)
    if m:
        return f"{m.group(1)}_{m.group(2)}"
    # D2_1 -> D2.1  (underscore to dot)
    m = _RE_UNDERSCORE_NOTATION.match(id_str)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return None


def validate_pattern(data: object, source: str) -> list[str]:
    """Return list of human-readable validation issues for a pattern dict.

    Errors (missing required field, invalid enum) are logged at WARNING so
    they surface in production but don't fail the load — a broken pattern
    is better than a broken server. Empty list means the pattern is clean.
    """
    issues: list[str] = []
    if not isinstance(data, dict):
        return [f"{source}: top-level YAML is not a mapping"]
    for field_ in REQUIRED_PATTERN_FIELDS:
        if not data.get(field_):
            issues.append(f"{source}: missing required field '{field_}'")
    ct = data.get("content_type")
    if ct and ct not in VALID_CONTENT_TYPES:
        issues.append(f"{source}: invalid content_type '{ct}'")
    elif ct in CONTENT_TYPE_REQUIRED_BLOCKS:
        for block_field in CONTENT_TYPE_REQUIRED_BLOCKS[ct]:
            if not data.get(block_field):
                issues.append(
                    f"{source}: content_type '{ct}' requires field '{block_field}'"
                )
    cf = data.get("confidence")
    if cf and cf not in VALID_CONFIDENCES:
        issues.append(f"{source}: invalid confidence '{cf}'")
    anchors = data.get("normative_anchors")
    if anchors and not isinstance(anchors, dict):
        issues.append(f"{source}: normative_anchors must be a mapping")
    elif isinstance(anchors, dict):
        for key in NORMATIVE_ANCHOR_KEYS:
            if key not in anchors or not isinstance(anchors[key], list):
                issues.append(
                    f"{source}: normative_anchors missing list '{key}'"
                )
    vc = data.get("version_compat")
    if vc and not isinstance(vc, dict):
        issues.append(f"{source}: version_compat must be a mapping (got {type(vc).__name__})")
    elif isinstance(vc, dict):
        for key in VERSION_COMPAT_KEYS:
            if not vc.get(key):
                issues.append(f"{source}: version_compat missing '{key}'")
    return issues


@dataclass
class Subgoal:
    pattern_id: str
    display_id: str
    suite_id: str
    suite_title: str
    suite_type: str  # "driver" | "inhibitor"
    title: str
    description: str
    sfrs: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    # Canonical flag from criteria-v1.json — NOT derived from the pattern YAML.
    # This is the source of truth; patterns that carry their own flag are
    # superseded at load time.
    is_underlined_variant: bool = False
    # Pattern layer (may be None if no pattern drafted yet)
    pattern: dict | None = None
    # True when the pattern was resolved via dot-underscore fallback,
    # meaning the pattern is borrowed from the base subgoal rather than
    # being variant-specific.
    is_variant_fallback: bool = False

    @property
    def has_pattern(self) -> bool:
        return self.pattern is not None

    @property
    def content_type(self) -> str | None:
        return self.pattern.get("content_type") if self.pattern else None

    @property
    def confidence(self) -> str | None:
        return self.pattern.get("confidence") if self.pattern else None


@dataclass
class FrameworkIndex:
    version: str
    subgoals: dict[str, Subgoal]  # pattern_id -> Subgoal
    by_display_id: dict[str, list[str]]  # display_id -> [pattern_id]
    by_suite: dict[str, list[str]]  # suite_id -> [pattern_id]
    suites: dict[str, dict]  # suite_id -> suite metadata
    validation_issues: list[str] = field(default_factory=list)
    source_mtime: float = 0.0
    loaded_at: float = 0.0
    # Reverse cross-reference graph: pattern_id -> list of pattern_ids that reference it.
    reverse_xrefs: dict[str, list[str]] = field(default_factory=dict)

    def get(self, key: str) -> Subgoal | None:
        """Resolve by pattern_id or display_id (returns first match for display_id)."""
        if key in self.subgoals:
            return self.subgoals[key]
        pids = self.by_display_id.get(key, [])
        if pids:
            return self.subgoals[pids[0]]
        return None

    def resolve_all(self, key: str) -> list[Subgoal]:
        """Like get() but returns all matches for display_id collisions."""
        if key in self.subgoals:
            return [self.subgoals[key]]
        pids = self.by_display_id.get(key, [])
        return [self.subgoals[p] for p in pids]


def _slugify(title: str, max_len: int = 40) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
    slug = "-".join(s for s in slug.split("-") if s)
    return slug[:max_len]


def _derive_pattern_id(suite_id: str, index: int, title: str) -> str:
    return f"{suite_id}::idx{index}::{_slugify(title)}"


def _load_pattern_yamls() -> tuple[dict[str, dict], list[str], float]:
    """Walk suites/ and return (pattern_id -> dict, validation_issues, mtime_ceiling).

    mtime_ceiling is the latest mtime across all loaded files; used by the
    hot-reload check.
    """
    out: dict[str, dict] = {}
    issues: list[str] = []
    newest_mtime = 0.0

    if not SUITES_DIR.exists():
        return out, issues, newest_mtime

    for suite_dir in sorted(SUITES_DIR.iterdir()):
        if not suite_dir.is_dir():
            continue
        for yf in sorted(suite_dir.glob("*.yaml")):
            newest_mtime = max(newest_mtime, yf.stat().st_mtime)
            try:
                data = yaml.load(yf.read_text(), Loader=_YamlLoader)
            except yaml.YAMLError as e:
                issues.append(f"{yf.name}: YAML parse error: {e}")
                continue
            src = str(yf.relative_to(REPO_ROOT))
            file_issues = validate_pattern(data, src)
            if file_issues:
                issues.extend(file_issues)
                for i in file_issues:
                    log.warning(i)
            if isinstance(data, dict) and data.get("id"):
                out[data["id"]] = data
            elif isinstance(data, dict):
                issues.append(f"{yf.name}: pattern has no 'id' field, skipped")

    # Exemplars load with same validation discipline.
    if EXEMPLARS_DIR.exists():
        for yf in sorted(EXEMPLARS_DIR.glob("*.yaml")):
            newest_mtime = max(newest_mtime, yf.stat().st_mtime)
            try:
                data = yaml.load(yf.read_text(), Loader=_YamlLoader)
            except yaml.YAMLError as e:
                issues.append(f"exemplar {yf.name}: YAML parse error: {e}")
                continue
            if isinstance(data, dict) and data.get("id"):
                out.setdefault(data["id"], data)

    return out, issues, newest_mtime


def load_framework() -> FrameworkIndex:
    """Build the in-memory index."""
    if not CRITERIA_PATH.exists():
        raise FileNotFoundError(
            f"criteria file not found: {CRITERIA_PATH}. Expected the assessor's "
            f"extracted criteria JSON."
        )
    try:
        criteria = json.loads(CRITERIA_PATH.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"criteria file is malformed JSON ({CRITERIA_PATH}): {e}"
        ) from e
    criteria_mtime = CRITERIA_PATH.stat().st_mtime
    pattern_by_id, validation_issues, suites_mtime = _load_pattern_yamls()

    # Build an auxiliary lookup: (suite_id, display_id) -> pattern dict
    # so exemplar-shortform ids resolve onto the composite pattern_id.
    pattern_by_suite_display: dict[tuple[str, str], dict] = {}
    for pid, pdata in pattern_by_id.items():
        key = (pdata.get("suite_id", ""), pdata.get("display_id", ""))
        pattern_by_suite_display.setdefault(key, pdata)

    subgoals: dict[str, Subgoal] = {}
    by_display_id: dict[str, list[str]] = {}
    by_suite: dict[str, list[str]] = {}
    suites_meta: dict[str, dict] = {}

    for suite in criteria.get("suites", []):
        suite_id = suite["id"]
        suite_title = suite["title"]
        suite_type = suite["type"]
        suites_meta[suite_id] = {
            "id": suite_id,
            "title": suite_title,
            "type": suite_type,
            "subgoal_count": len(suite.get("subgoals", [])),
        }
        by_suite.setdefault(suite_id, [])

        for idx, sg in enumerate(suite.get("subgoals", [])):
            pid = _derive_pattern_id(suite_id, idx, sg["title"])
            sg_display_id = sg.get("id", "")
            # Resolve pattern with fallback detection: the third branch
            # (alternate notation) means the pattern is borrowed from the
            # base subgoal rather than being variant-specific.
            pattern = pattern_by_id.get(pid)
            variant_fallback = False
            if pattern is None:
                pattern = pattern_by_suite_display.get((suite_id, sg_display_id))
            if pattern is None:
                # Fallback: try alternate notation (dot <-> underscore) so
                # pattern YAMLs with old dot-notation display_ids still match
                # criteria entries that now use underscore notation, and vice versa.
                pattern = pattern_by_suite_display.get(
                    (suite_id, _alternate_id_notation(sg_display_id) or "")
                )
                if pattern is not None:
                    variant_fallback = True
            s = Subgoal(
                pattern_id=pid,
                display_id=sg.get("id", ""),
                suite_id=suite_id,
                suite_title=suite_title,
                suite_type=suite_type,
                title=sg.get("title", ""),
                description=sg.get("description", ""),
                sfrs=sg.get("sfrs", []),
                evidence=sg.get("evidence", []),
                is_underlined_variant=bool(sg.get("isUnderlinedVariant", False)),
                pattern=pattern,
                is_variant_fallback=variant_fallback,
            )
            subgoals[pid] = s
            by_display_id.setdefault(s.display_id, []).append(pid)
            by_suite[suite_id].append(pid)

    # Build reverse cross-reference index.
    reverse_xrefs: dict[str, list[str]] = {}
    for pid, sg in subgoals.items():
        if not sg.pattern:
            continue
        refs = sg.pattern.get("cross_references") or []
        if isinstance(refs, str):
            refs = [refs]
        for ref in refs:
            if ref in subgoals:
                reverse_xrefs.setdefault(ref, []).append(pid)
            else:
                msg = f"unresolved cross_reference '{ref}' in pattern '{pid}'"
                validation_issues.append(msg)
                log.warning(msg)

    idx = FrameworkIndex(
        version=criteria.get("version", "unknown"),
        subgoals=subgoals,
        by_display_id=by_display_id,
        by_suite=by_suite,
        suites=suites_meta,
        validation_issues=validation_issues,
        source_mtime=max(criteria_mtime, suites_mtime),
        loaded_at=time.time(),
        reverse_xrefs=reverse_xrefs,
    )
    if validation_issues:
        log.warning(
            "FrameworkIndex loaded with %d validation issues (patterns still served)",
            len(validation_issues),
        )
    return idx


_freshness_cache: dict[str, Any] = {"result": None, "timestamp": 0.0, "source_mtime": 0.0}


def newer_source_exists(idx: FrameworkIndex) -> bool:
    """True if any pattern/criteria file on disk is newer than the loaded index.

    Used by the server's hot-reload path so edits in `research/mcp/suites/`
    show up without a restart.

    Caches the result for 2 seconds to avoid stat-walking ~230 files on every
    tool dispatch when multiple calls arrive in quick succession.
    """
    now = time.time()
    if (
        now - _freshness_cache["timestamp"] < 2.0
        and _freshness_cache["source_mtime"] == idx.source_mtime
    ):
        return _freshness_cache["result"]  # type: ignore[return-value]

    latest = 0.0
    try:
        latest = max(latest, CRITERIA_PATH.stat().st_mtime)
    except FileNotFoundError:
        pass
    if SUITES_DIR.exists():
        for suite_dir in SUITES_DIR.iterdir():
            if not suite_dir.is_dir():
                continue
            for yf in suite_dir.glob("*.yaml"):
                try:
                    latest = max(latest, yf.stat().st_mtime)
                except FileNotFoundError:
                    pass
    if EXEMPLARS_DIR.exists():
        for yf in EXEMPLARS_DIR.glob("*.yaml"):
            try:
                latest = max(latest, yf.stat().st_mtime)
            except FileNotFoundError:
                pass

    result = latest > idx.source_mtime
    _freshness_cache["result"] = result
    _freshness_cache["timestamp"] = now
    _freshness_cache["source_mtime"] = idx.source_mtime
    return result


def subgoal_to_dict(s: Subgoal, include_pattern: bool = True) -> dict[str, Any]:
    """Render a Subgoal as a JSON-serialisable dict for the MCP tool responses."""
    out: dict[str, Any] = {
        "pattern_id": s.pattern_id,
        "display_id": s.display_id,
        "suite_id": s.suite_id,
        "suite_title": s.suite_title,
        "suite_type": s.suite_type,
        "title": s.title,
        "description": s.description,
        "sfrs": s.sfrs,
        "evidence": s.evidence,
        "has_pattern": s.has_pattern,
    }
    # Always surface is_underlined_variant from the canonical source,
    # not the (potentially out-of-sync) pattern YAML.
    out["is_underlined_variant"] = s.is_underlined_variant
    # True when the pattern was resolved via dot-underscore fallback,
    # meaning the pattern is borrowed from the base subgoal, not variant-specific.
    out["is_variant_fallback"] = s.is_variant_fallback
    # Other reliability metadata comes from the pattern YAML.
    if s.pattern:
        out["content_type"] = s.pattern.get("content_type")
        out["confidence"] = s.pattern.get("confidence")
        out["needs_human_review"] = s.pattern.get("needs_human_review")
        out["reviewed_by"] = s.pattern.get("reviewed_by")
    if include_pattern and s.pattern:
        out["pattern"] = s.pattern
    return out


# ---------------------------------------------------------------------------
# Operational Heuristics layer
# ---------------------------------------------------------------------------

HEURISTICS_PATH = SUITES_DIR.parent / "operational_heuristics.yaml"


@dataclass
class OperationalHeuristic:
    id: str
    title: str
    principle: str
    origin: str
    framework_mapping: list[dict] = field(default_factory=list)
    evidence_sources: list[dict] = field(default_factory=list)
    design_patterns: list[dict] = field(default_factory=list)
    anti_patterns: list[dict] = field(default_factory=list)
    discovery_narrative: str = ""
    confidence: str = ""   # "high", "medium", "low" — optional
    source: str = ""       # provenance description — optional


@dataclass
class HeuristicsIndex:
    version: str
    heuristics: dict[str, OperationalHeuristic]
    source_mtime: float = 0.0
    loaded_at: float = 0.0


def load_heuristics() -> HeuristicsIndex:
    """Load operational heuristics from the YAML file."""
    if not HEURISTICS_PATH.exists():
        log.warning(
            "operational_heuristics.yaml not found at %s — the heuristics "
            "layer will be EMPTY (list_operational_heuristics returns no "
            "results). If this is a bundled install, the wheel was likely "
            "built without running scripts/sync-data.sh.",
            HEURISTICS_PATH,
        )
        return HeuristicsIndex(
            version="1.0", heuristics={}, source_mtime=0.0, loaded_at=time.time()
        )

    try:
        data = yaml.load(HEURISTICS_PATH.read_text(), Loader=_YamlLoader)
    except yaml.YAMLError as e:
        log.warning(f"operational_heuristics.yaml: YAML parse error: {e}")
        return HeuristicsIndex(
            version="1.0", heuristics={}, source_mtime=0.0, loaded_at=time.time()
        )
    if not isinstance(data, dict):
        data = {}
    mtime = HEURISTICS_PATH.stat().st_mtime

    heuristics: dict[str, OperationalHeuristic] = {}
    for entry in data.get("heuristics", []):
        try:
            h = OperationalHeuristic(
                id=entry["id"],
                title=entry["title"],
                principle=entry["principle"],
                origin=entry.get("origin", ""),
                framework_mapping=entry.get("framework_mapping", []),
                evidence_sources=entry.get("evidence_sources", []),
                design_patterns=entry.get("design_patterns", []),
                anti_patterns=entry.get("anti_patterns", []),
                discovery_narrative=entry.get("discovery_narrative", ""),
                confidence=entry.get("confidence", ""),
                source=entry.get("source", ""),
            )
            heuristics[h.id] = h
        except (KeyError, TypeError) as e:
            log.warning(f"Skipping malformed heuristic entry: {e}")

    return HeuristicsIndex(
        version=data.get("version", "1.0"),
        heuristics=heuristics,
        source_mtime=mtime,
        loaded_at=time.time(),
    )


def newer_heuristics_exist(idx: HeuristicsIndex) -> bool:
    """True if the heuristics file on disk is newer than the loaded index."""
    if not HEURISTICS_PATH.exists():
        return False
    return HEURISTICS_PATH.stat().st_mtime > idx.source_mtime


def heuristic_to_dict(h: OperationalHeuristic) -> dict[str, Any]:
    """Render an OperationalHeuristic as a JSON-serialisable dict."""
    out: dict[str, Any] = {
        "id": h.id,
        "title": h.title,
        "principle": h.principle,
        "origin": h.origin,
        "framework_mapping": h.framework_mapping,
        "evidence_sources": h.evidence_sources,
        "design_patterns": h.design_patterns,
        "anti_patterns": h.anti_patterns,
        "discovery_narrative": h.discovery_narrative,
    }
    if h.confidence:
        out["confidence"] = h.confidence
    if h.source:
        out["source"] = h.source
    return out
