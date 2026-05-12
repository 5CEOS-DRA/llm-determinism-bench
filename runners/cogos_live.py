"""
CogOS live-gateway runner.

Hits the production cogos-api gateway at the URL pinned below, using a
customer-equivalent bearer token. This is the runner that closes the
"audit, not trust" loop: the same bench any customer can run, executed
against the same live endpoint, on the published cadence in
.github/workflows/audit.yml.

- Endpoint: COGOS_LIVE_URL env (default below)
- Auth:     COGOS_LIVE_API_KEY env (sk-cogos-...; customer-equivalent key)
- Modes:
  - "default" — prompt-only, no response_format.
  - "best"    — response_format: json_schema with strict=true (the
                grammar-constrained-decoding mode CogOS sells against).

Single-call runner. Mirrors `runners.ollama.run_ollama_once` shape so
the harness loop can route across systems uniformly.
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

DEFAULT_URL = "https://cogos-api.proudsea-75ca2c6f.eastus.azurecontainerapps.io/v1/chat/completions"


@dataclass(frozen=True)
class CogosLiveRunResult:
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
    # Cogos-specific extension fields (from response.cogos.{...} and headers)
    cogos_latency_ms: Optional[int]
    cogos_request_id: Optional[str]
    cogos_schema_enforced: Optional[bool]
    cogos_quota_limit: Optional[int]
    cogos_quota_remaining: Optional[int]


def _build_messages(system_prompt: str, user_prompt: str) -> list:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _payload_default(model: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "temperature": 0.0,
    }


def _payload_best(model: str, system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": _build_messages(system_prompt, user_prompt),
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "bench_output",
                "strict": True,
                "schema": schema,
            },
        },
    }


def run_cogos_live_once(
    *,
    system: str,
    mode: Mode,
    parser_mode: ParserMode,
    model: str,
    scenario_id: str,
    schema_id: str,
    system_prompt: str,
    user_prompt: str,
    schema: Optional[Dict[str, Any]],
    timeout_seconds: float = 90.0,
) -> CogosLiveRunResult:
    api_key = os.environ.get("COGOS_LIVE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "COGOS_LIVE_API_KEY not set — the live runner needs a "
            "customer-equivalent bearer token (sk-cogos-...)."
        )
    url = os.environ.get("COGOS_LIVE_URL", DEFAULT_URL)

    payload: Dict[str, Any]
    if mode == "best":
        if schema is None:
            raise ValueError("best mode requires a schema")
        payload = _payload_best(model, system_prompt, user_prompt, schema)
    else:
        payload = _payload_default(model, system_prompt, user_prompt)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    started = time.monotonic()
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
    elapsed = time.monotonic() - started

    try:
        body = resp.json()
    except Exception:
        body = {}

    content = ""
    if isinstance(body, dict):
        choices = body.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = msg.get("content", "") or ""

    if mode == "best":
        parsed, parse_err = parse_strict(content)
    elif parser_mode == "permissive":
        parsed, parse_err = parse_permissive(content)
    else:
        parsed, parse_err = parse_strict(content)

    if parsed is None or schema is None:
        schema_ok, schema_result = False, None
    else:
        sr = validate(parsed, schema)
        schema_ok = sr.ok
        schema_result = sr

    cogos_block = body.get("cogos", {}) if isinstance(body, dict) else {}

    def _i(h: str) -> Optional[int]:
        v = resp.headers.get(h)
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    return CogosLiveRunResult(
        system=system,
        mode=mode,
        parser_mode=parser_mode,
        model=model,
        scenario_id=scenario_id,
        schema_id=schema_id,
        raw_output=content,
        parse_ok=parsed is not None,
        parse_error=parse_err,
        schema_ok=schema_ok,
        schema_result=schema_result,
        latency_seconds=elapsed,
        cogos_latency_ms=cogos_block.get("latency_ms") if isinstance(cogos_block, dict) else None,
        cogos_request_id=cogos_block.get("request_id") if isinstance(cogos_block, dict) else None,
        cogos_schema_enforced=cogos_block.get("schema_enforced") if isinstance(cogos_block, dict) else None,
        cogos_quota_limit=_i("x-cogos-quota-limit"),
        cogos_quota_remaining=_i("x-cogos-quota-remaining"),
    )
