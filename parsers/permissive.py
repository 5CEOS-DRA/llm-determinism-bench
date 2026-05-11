"""
Permissive JSON parser.

SPEC v0.2 §3.3 contract:
- Strip leading/trailing Markdown fences (``` with optional language tag).
- No other heuristics, no regex surgery on the body.
- Delegate to parse_strict on the stripped output.
- Return the same ParseResult type.

If no fences are present, this behaves identically to parse_strict.
If fences are stripped, the inner body must still be valid JSON;
otherwise we hard-fail with the strict parser's error.
"""
from __future__ import annotations

import re

from .strict import ParseResult, parse_strict

# Opening fence: ``` optionally followed by a language tag (any non-newline
# chars), then a newline. Outer whitespace permitted.
_OPEN_FENCE = re.compile(r"^\s*```[^\n]*\n")

# Closing fence: newline, then ``` at the very end (trailing whitespace
# permitted).
_CLOSE_FENCE = re.compile(r"\n\s*```\s*$")


def _strip_fences(raw: str) -> str:
    body = raw.strip()
    body = _OPEN_FENCE.sub("", body, count=1)
    body = _CLOSE_FENCE.sub("", body, count=1)
    return body.strip()


def parse_permissive(raw: str) -> ParseResult:
    return parse_strict(_strip_fences(raw))
