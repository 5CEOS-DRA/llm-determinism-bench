"""
Cloud Provider B runner.

Connects to a hosted chat-completions endpoint at a third-party provider's
API (chat-completions-compatible shape, identical to Cloud A's contract).
The provider's identity is intentionally not surfaced in this file's
public-facing strings — the bench measures behavior, not brands. The API
URL constant below documents what this runner actually hits so anyone
running the bench can verify what's being measured.

- Endpoint: see API_URL constant below (factual technical reference)
- Auth: bearer token in CLOUD_B_API_KEY env var
- Free tier signup typically available at the provider's website.
- Modes:
  - "default" — prompt-only.
  - "best"    — response_format: json_schema with strict=true.

Mirrors runners.cloud_a.run_cloud_a_once exactly except for endpoint, auth
env var, and the `system` label.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import requests

from parsers.permissive import parse_permissive
from parsers.schema import SchemaResult, validate
from parsers.strict import parse_strict


Mode = Literal["default", "best"]
ParserMode = Literal["strict", "permissive"]

API_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass(frozen=True)
class CloudBRunResult:
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
    system_fingerprint: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]


def _build_messages(system_prompt: str, user_prompt: str) -> list:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _payload_default(
    model: str, system_prompt: str, user_prompt: str, seed: int
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "temperature": 0.0,
        "stream": False,
        "seed": seed,
    }


def _payload_best(
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    schema_id: str,
    seed: int,
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "temperature": 0.0,
        "stream": False,
        "seed": seed,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_id,
                "strict": True,
                "schema": schema,
            },
        },
    }


def _call_cloud(
    payload: Dict[str, Any], api_key: str, timeout: float = 60.0
) -> Dict[str, Any]:
    resp = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def run_cloud_b_once(
    *,
    mode: Mode,
    parser_mode: ParserMode,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: Dict[str, Any],
    scenario_id: str,
    schema_id: str,
    seed: int = 0,
) -> CloudBRunResult:
    api_key = os.environ.get("CLOUD_B_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CLOUD_B_API_KEY not set. Export it before running the Cloud Provider B runner."
        )

    if mode == "default":
        payload = _payload_default(model, system_prompt, user_prompt, seed)
    elif mode == "best":
        payload = _payload_best(
            model, system_prompt, user_prompt, schema, schema_id, seed
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    t0 = time.perf_counter()
    data = _call_cloud(payload, api_key)
    latency = time.perf_counter() - t0

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Cloud B response had no choices: {data!r}")
    raw = choices[0].get("message", {}).get("content")
    if not isinstance(raw, str):
        raise RuntimeError(f"Unexpected Cloud B response shape: {data!r}")

    system_fingerprint = data.get("system_fingerprint")
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

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

    return CloudBRunResult(
        system=f"cloud-b-{model}",
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
        system_fingerprint=system_fingerprint,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
