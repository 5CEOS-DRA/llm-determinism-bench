"""
JSON Schema validator (deterministic).

SPEC v0.2 §3.1 + §5 contract:
- Input: parsed Python value (from parsers.strict / parsers.permissive)
  plus a JSON Schema dict.
- Output: SchemaResult — categorized errors the harness can aggregate.
- Backed by `jsonschema` (Draft 2020-12) with format checking enabled.
- Errors emitted in deterministic order (sorted by absolute path).

Error categories (from §3.1):
- extra_fields       — additionalProperties violations
- missing_required   — required violations
- enum_violations    — enum violations
- format_violations  — format violations (e.g. date-time)
- other_errors       — everything else (type mismatch, range, length, etc.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from jsonschema import Draft202012Validator, FormatChecker


@dataclass(frozen=True)
class SchemaResult:
    ok: bool
    errors: Tuple[str, ...] = ()
    extra_fields: Tuple[str, ...] = ()
    missing_required: Tuple[str, ...] = ()
    enum_violations: Tuple[str, ...] = ()
    format_violations: Tuple[str, ...] = ()
    other_errors: Tuple[str, ...] = ()


def _path_str(path) -> str:
    parts = []
    for p in path:
        if isinstance(p, int):
            parts.append(f"[{p}]")
        else:
            parts.append(f".{p}" if parts else str(p))
    return "".join(parts) if parts else "<root>"


def validate(value: Any, schema: dict) -> SchemaResult:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    extra: list = []
    required: list = []
    enums: list = []
    formats: list = []
    others: list = []
    all_errs: list = []

    errors = sorted(
        validator.iter_errors(value),
        key=lambda e: (tuple(str(p) for p in e.absolute_path), e.validator or ""),
    )

    for err in errors:
        path = _path_str(err.absolute_path)
        msg = f"{path}: {err.message}"
        all_errs.append(msg)
        kind = err.validator
        if kind == "additionalProperties":
            extra.append(msg)
        elif kind == "required":
            required.append(msg)
        elif kind == "enum":
            enums.append(msg)
        elif kind == "format":
            formats.append(msg)
        else:
            others.append(msg)

    return SchemaResult(
        ok=len(all_errs) == 0,
        errors=tuple(all_errs),
        extra_fields=tuple(extra),
        missing_required=tuple(required),
        enum_violations=tuple(enums),
        format_violations=tuple(formats),
        other_errors=tuple(others),
    )
