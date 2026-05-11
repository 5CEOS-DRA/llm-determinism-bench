"""
Ollama runner for the cogOS side of the benchmark.

- Models: qwen2.5:3b-instruct (Tier B primary), qwen2.5:7b-instruct (secondary).
- Endpoint: http://localhost:11434/api/chat
- Modes:
  - "default" — prompt-only, no structured output.
  - "best"    — Ollama 0.5+ structured output via `format` (JSON Schema).

Single-call runner. The harness loops over scenarios/schemas/modes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import requests

from parsers.permissive import parse_permissive
from parsers.schema import SchemaResult, validate
from parsers.strict import parse_strict


Mode = Literal["default", "best"]
ParserMode = Literal["strict", "permissive"]


@dataclass(frozen=True)
class OllamaRunResult:
    system: str
    mode: Mode
    parser_mode: ParserMode
    model: str
    scenario_id: str
    schema_id: str
    raw_output: str
    parse_ok: bool
    parse_error: Optional[str]
    schema_ok: bool
    schema_result: Optional[SchemaResult]
    latency_seconds: float


def _build_messages(system_prompt: str, user_prompt: str) -> list:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _payload_default(model: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "options": {"temperature": 0.0},
    }


def _payload_best(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    # Ollama 0.5+ structured output: pass JSON Schema dict as `format`.
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "stream": False,
        "options": {"temperature": 0.0},
        "format": schema,
    }


def _call_ollama(payload: Dict[str, Any], timeout: float = 60.0) -> str:
    resp = requests.post(
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"Unexpected Ollama response shape: {data!r}")
    return content


def run_ollama_once(
    *,
    mode: Mode,
    parser_mode: ParserMode,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    scenario_id: str,
    schema_id: str,
) -> OllamaRunResult:
    if mode == "default":
        payload = _payload_default(model, system_prompt, user_prompt)
    elif mode == "best":
        payload = _payload_best(model, system_prompt, user_prompt, schema)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    t0 = time.perf_counter()
    raw = _call_ollama(payload)
    latency = time.perf_counter() - t0

    if parser_mode == "strict":
        parsed = parse_strict(raw)
    elif parser_mode == "permissive":
        parsed = parse_permissive(raw)
    else:
        raise ValueError(f"Unknown parser_mode: {parser_mode}")

    if parsed.ok:
        schema_result: Optional[SchemaResult] = validate(parsed.value, schema)
        schema_ok = schema_result.ok
    else:
        schema_result = None
        schema_ok = False

    return OllamaRunResult(
        system=f"cogOS-ollama-{model}",
        mode=mode,
        parser_mode=parser_mode,
        model=model,
        scenario_id=scenario_id,
        schema_id=schema_id,
        raw_output=raw,
        parse_ok=parsed.ok,
        parse_error=parsed.error,
        schema_ok=schema_ok,
        schema_result=schema_result,
        latency_seconds=latency,
    )
