"""
Scenario-specific semantic-correctness rubrics (SPEC v0.3 §6.1).

These run AFTER schema validation. They answer the gameable-validity question:
"did the model actually answer the scenario, or just emit valid filler?"

For Tier 1/2 the rubrics are explicit and deterministic. For Tier 3 the
rubrics are labeled necessary-but-not-sufficient — a model can pass with
filler words. Acceptable for v0.3.

Deadline interpretation uses the fixed clock from SPEC §6.1:
FAKE_NOW = 2026-05-10T12:00:00Z

All rubrics return RubricResult(ok, failures).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List


FAKE_NOW = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RubricResult:
    ok: bool
    failures: List[str] = field(default_factory=list)


# -------- helpers -----------------------------------------------------------

def _parse_dt(s: str) -> datetime:
    """Parse ISO 8601 datetime. Normalize 'Z' suffix to '+00:00' for py<=3.10."""
    if not isinstance(s, str):
        raise ValueError(f"expected datetime string, got {type(s).__name__}")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _expect_eq(actual: Any, expected: Any, label: str, fails: List[str]) -> None:
    if actual != expected:
        fails.append(f"{label} should be {expected!r}, got {actual!r}")


def _expect_in(needle: Any, haystack: Any, label: str, fails: List[str]) -> None:
    if not isinstance(haystack, (list, str)) or needle not in haystack:
        fails.append(f"{label} should include {needle!r}, got {haystack!r}")


def _expect_contains_substr(haystack: str, needles: List[str], label: str, fails: List[str]) -> None:
    if not isinstance(haystack, str):
        fails.append(f"{label} should be string, got {type(haystack).__name__}")
        return
    hay = haystack.lower()
    for n in needles:
        if n not in hay:
            fails.append(f"{label} should mention {n!r}")


def _expect_deadline(actual: str, expected_iso: str, label: str, fails: List[str]) -> None:
    try:
        a = _parse_dt(actual)
        e = _parse_dt(expected_iso)
    except Exception as exc:  # noqa: BLE001
        fails.append(f"{label} parse error: {exc}")
        return
    if a != e:
        fails.append(f"{label} should be {expected_iso}, got {actual!r}")


# -------- Tier 1 rubrics ----------------------------------------------------

def _t1s1(v: Dict[str, Any]) -> RubricResult:
    """Review incident summary, high, tags incident+review."""
    f: List[str] = []
    _expect_eq(v.get("priority"), "high", "priority", f)
    _expect_in("incident", v.get("tags"), "tags", f)
    _expect_in("review", v.get("tags"), "tags", f)
    return RubricResult(not f, f)


def _t1s2(v: Dict[str, Any]) -> RubricResult:
    """Status update, low, tags communication+status."""
    f: List[str] = []
    _expect_eq(v.get("priority"), "low", "priority", f)
    _expect_in("communication", v.get("tags"), "tags", f)
    _expect_in("status", v.get("tags"), "tags", f)
    return RubricResult(not f, f)


def _t1s3(v: Dict[str, Any]) -> RubricResult:
    """Backup logs, medium, tags backup+logs."""
    f: List[str] = []
    _expect_eq(v.get("priority"), "medium", "priority", f)
    _expect_in("backup", v.get("tags"), "tags", f)
    _expect_in("logs", v.get("tags"), "tags", f)
    return RubricResult(not f, f)


# -------- Tier 2 rubrics ----------------------------------------------------

def _t2s1(v: Dict[str, Any]) -> RubricResult:
    """op-1742 verify routing logs, three steps, tomorrow 17:00 UTC."""
    f: List[str] = []
    _expect_eq(v.get("user", {}).get("id"), "op-1742", "user.id", f)
    _expect_eq(v.get("user", {}).get("role"), "operator", "user.role", f)
    steps = v.get("task", {}).get("steps") or []
    if len(steps) != 3:
        f.append(f"task.steps should have exactly 3, got {len(steps)}")
    _expect_deadline(v.get("deadline", ""), "2026-05-11T17:00:00+00:00", "deadline", f)
    return RubricResult(not f, f)


def _t2s2(v: Dict[str, Any]) -> RubricResult:
    """an-8831 review eval metrics, at least two steps, two days from now at 09:00 UTC."""
    f: List[str] = []
    _expect_eq(v.get("user", {}).get("id"), "an-8831", "user.id", f)
    _expect_eq(v.get("user", {}).get("role"), "analyst", "user.role", f)
    steps = v.get("task", {}).get("steps") or []
    if len(steps) < 2:
        f.append(f"task.steps should have >=2, got {len(steps)}")
    _expect_deadline(v.get("deadline", ""), "2026-05-12T09:00:00+00:00", "deadline", f)
    return RubricResult(not f, f)


def _t2s3(v: Dict[str, Any]) -> RubricResult:
    """vw-2209 confirm deployment notes archived, one step, today at 23:00 UTC."""
    f: List[str] = []
    _expect_eq(v.get("user", {}).get("id"), "vw-2209", "user.id", f)
    _expect_eq(v.get("user", {}).get("role"), "viewer", "user.role", f)
    steps = v.get("task", {}).get("steps") or []
    if len(steps) != 1:
        f.append(f"task.steps should have exactly 1, got {len(steps)}")
    _expect_deadline(v.get("deadline", ""), "2026-05-10T23:00:00+00:00", "deadline", f)
    return RubricResult(not f, f)


# -------- Tier 3 rubrics (necessary-not-sufficient) -------------------------

def _t3s1(v: Dict[str, Any]) -> RubricResult:
    """Summarize 2-page incident report, deterministic, strict latency, low cost."""
    f: List[str] = []
    _expect_eq(v.get("intent", {}).get("normalized_type"), "summarization", "intent.normalized_type", f)
    _expect_eq(v.get("constraints", {}).get("must_be_deterministic"), True, "constraints.must_be_deterministic", f)
    _expect_contains_substr(v.get("routing", {}).get("explanation", ""), ["latency", "cost"], "routing.explanation", f)
    return RubricResult(not f, f)


def _t3s2(v: Dict[str, Any]) -> RubricResult:
    """Classify short customer message, latency min, cost low, deterministic."""
    f: List[str] = []
    _expect_eq(v.get("intent", {}).get("normalized_type"), "classification", "intent.normalized_type", f)
    _expect_eq(v.get("constraints", {}).get("must_be_deterministic"), True, "constraints.must_be_deterministic", f)
    _expect_contains_substr(v.get("routing", {}).get("explanation", ""), ["latency", "cost"], "routing.explanation", f)
    return RubricResult(not f, f)


def _t3s3(v: Dict[str, Any]) -> RubricResult:
    """Extract key fields from system-health note. Per v0.3 enum mapping = classification."""
    f: List[str] = []
    _expect_eq(v.get("intent", {}).get("normalized_type"), "classification", "intent.normalized_type", f)
    _expect_eq(v.get("constraints", {}).get("must_be_deterministic"), True, "constraints.must_be_deterministic", f)
    _expect_contains_substr(v.get("routing", {}).get("explanation", ""), ["latency", "cost"], "routing.explanation", f)
    return RubricResult(not f, f)


RUBRICS: Dict[str, Callable[[Dict[str, Any]], RubricResult]] = {
    "tier1_scenario1": _t1s1,
    "tier1_scenario2": _t1s2,
    "tier1_scenario3": _t1s3,
    "tier2_scenario1": _t2s1,
    "tier2_scenario2": _t2s2,
    "tier2_scenario3": _t2s3,
    "tier3_scenario1": _t3s1,
    "tier3_scenario2": _t3s2,
    "tier3_scenario3": _t3s3,
}


def evaluate(scenario_id: str, value: Any) -> RubricResult:
    """Apply rubric for a scenario to a parsed JSON value. Missing rubric = vacuous pass."""
    rubric = RUBRICS.get(scenario_id)
    if rubric is None:
        return RubricResult(True, [])
    if not isinstance(value, dict):
        return RubricResult(False, [f"value is not a dict (got {type(value).__name__})"])
    try:
        return rubric(value)
    except Exception as exc:  # noqa: BLE001
        return RubricResult(False, [f"rubric exception: {type(exc).__name__}: {exc}"])
