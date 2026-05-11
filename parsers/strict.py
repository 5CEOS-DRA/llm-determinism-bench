"""
Strict JSON parser.

SPEC v0.2 §3.3 contract:
- Input: raw model output (str).
- Output: parsed object on success.
- Hard failure on any surrounding text, fences, or prose.
- No heuristics, no regex surgery, no fence stripping.

This is the lowest-entropy primitive of the harness. The permissive
parser (separate module) wraps this one: it strips fences, then
delegates here. All schema-validity scoring composes on top of this.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParseResult:
    ok: bool
    value: Any | None = None
    error: str | None = None
    error_pos: int | None = None


def parse_strict(raw: str) -> ParseResult:
    """Parse raw model output as JSON, strictly.

    `json.loads` matches the `JSON.parse` semantics required by §3.3:
    rejects fences, prose, trailing commas, and any non-JSON content.
    Leading/trailing whitespace is permitted (consistent with
    `JSON.parse`); anything else is hard failure.
    """
    try:
        return ParseResult(ok=True, value=json.loads(raw))
    except json.JSONDecodeError as e:
        return ParseResult(ok=False, error=e.msg, error_pos=e.pos)
