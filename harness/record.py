"""
Unified bench record. All runners flow into BenchRecord for JSONL emission.

Per SPEC v0.3:
- Default mode → two records per HTTP call (strict + permissive parsing of the
  same raw_output). No second HTTP call — same bytes, two parses.
- Best mode → one record per HTTP call (strict parsing only; constrained
  decoding shouldn't emit fences).

The record is JSON-serializable (no dataclass-only fields).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from parsers.permissive import parse_permissive
from parsers.schema import SchemaResult, validate
from parsers.strict import parse_strict


@dataclass(frozen=True)
class BenchRecord:
    # Identity
    system: str
    model: str
    mode: str          # "default" | "best"
    parser_mode: str   # "strict" | "permissive"
    scenario_id: str
    schema_id: str
    run_index: int
    seed: int

    # Result
    raw_output: str
    parse_ok: bool
    parse_error: Optional[str]
    schema_ok: bool
    extra_fields: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    enum_violations: List[str] = field(default_factory=list)
    format_violations: List[str] = field(default_factory=list)
    other_errors: List[str] = field(default_factory=list)

    # Timing + provider metadata
    latency_seconds: float = 0.0
    system_fingerprint: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    # Bench meta
    timestamp_iso: str = ""
    fake_now_iso: str = ""

    def to_jsonl_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _schema_result_to_lists(sr: Optional[SchemaResult]) -> Dict[str, List[str]]:
    if sr is None:
        return {
            "extra_fields": [],
            "missing_required": [],
            "enum_violations": [],
            "format_violations": [],
            "other_errors": [],
        }
    return {
        "extra_fields": list(sr.extra_fields),
        "missing_required": list(sr.missing_required),
        "enum_violations": list(sr.enum_violations),
        "format_violations": list(sr.format_violations),
        "other_errors": list(sr.other_errors),
    }


def from_runner_result(
    *,
    result: Any,        # OllamaRunResult | OpenAIRunResult | GroqRunResult
    parser_mode: str,
    run_index: int,
    seed: int,
    schema: Dict[str, Any],
    timestamp_iso: str,
    fake_now_iso: str,
) -> BenchRecord:
    """
    Convert a runner-specific result into a BenchRecord.

    If `parser_mode` differs from the parser_mode the runner used internally,
    we re-parse the raw_output with the requested parser and re-validate.
    This lets us get both strict and permissive records from a single HTTP
    call without paying the network cost twice.
    """
    if parser_mode == result.parser_mode:
        # Reuse the runner's parse+validate output.
        sr = result.schema_result
        kind_lists = _schema_result_to_lists(sr)
        return BenchRecord(
            system=result.system,
            model=result.model,
            mode=result.mode,
            parser_mode=parser_mode,
            scenario_id=result.scenario_id,
            schema_id=result.schema_id,
            run_index=run_index,
            seed=seed,
            raw_output=result.raw_output,
            parse_ok=result.parse_ok,
            parse_error=result.parse_error,
            schema_ok=result.schema_ok,
            latency_seconds=result.latency_seconds,
            system_fingerprint=getattr(result, "system_fingerprint", None),
            prompt_tokens=getattr(result, "prompt_tokens", None),
            completion_tokens=getattr(result, "completion_tokens", None),
            timestamp_iso=timestamp_iso,
            fake_now_iso=fake_now_iso,
            **kind_lists,
        )

    # Re-parse the same raw output with the other parser.
    parser = parse_strict if parser_mode == "strict" else parse_permissive
    parsed = parser(result.raw_output)
    if parsed.ok:
        sr = validate(parsed.value, schema)
        schema_ok = sr.ok
    else:
        sr = None
        schema_ok = False
    kind_lists = _schema_result_to_lists(sr)
    return BenchRecord(
        system=result.system,
        model=result.model,
        mode=result.mode,
        parser_mode=parser_mode,
        scenario_id=result.scenario_id,
        schema_id=result.schema_id,
        run_index=run_index,
        seed=seed,
        raw_output=result.raw_output,
        parse_ok=parsed.ok,
        parse_error=parsed.error,
        schema_ok=schema_ok,
        latency_seconds=result.latency_seconds,
        system_fingerprint=getattr(result, "system_fingerprint", None),
        prompt_tokens=getattr(result, "prompt_tokens", None),
        completion_tokens=getattr(result, "completion_tokens", None),
        timestamp_iso=timestamp_iso,
        fake_now_iso=fake_now_iso,
        **kind_lists,
    )
