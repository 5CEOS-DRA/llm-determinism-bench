"""
Main benchmark loop.

Iterates (system × mode × scenario × n) and emits BenchRecord JSONL.

Per SPEC v0.3:
- Active systems auto-detected by env-key presence:
    cogOS always active (Ollama local)
    Cloud Provider B active if CLOUD_B_API_KEY set
    Cloud Provider A active if CLOUD_A_API_KEY set
- Default mode → 2 records per HTTP call (strict + permissive parsing).
- Best mode → 1 record per HTTP call (strict only; constrained decoding).
- Per-call exceptions are caught and recorded as failed-parse records so a
  single transient error doesn't kill the batch.
- Fixed `fake_now_iso` = SPEC §6.1 anchor (2026-05-10T12:00:00Z).

Usage:
    python -m harness.loop                          # full sample sizes
    BENCH_N1=3 BENCH_N3=2 python -m harness.loop    # override sample sizes
    BENCH_SYSTEMS=cogos-3b python -m harness.loop   # restrict systems
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from harness.record import BenchRecord, from_runner_result

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
PROMPTS_DIR = REPO_ROOT / "prompts"
RESULTS_DIR = REPO_ROOT / "results" / "raw"

FAKE_NOW_ISO = "2026-05-10T12:00:00Z"

SYSTEM_PROMPT = """You are a JSON-only generator.
Rules:
- Output MUST be valid JSON.
- Output MUST conform exactly to the provided JSON Schema.
- Do NOT include explanations, comments, or markdown.
- Do NOT add fields that are not in the schema.
- Do NOT omit required fields."""


# (tier, scenario_index) -> sample size for main runs
def sample_sizes() -> Dict[str, int]:
    return {
        "tier1": int(os.environ.get("BENCH_N1", "33")),
        "tier2": int(os.environ.get("BENCH_N2", "33")),
        "tier3": int(os.environ.get("BENCH_N3", "10")),
    }


# -------- System registry ---------------------------------------------------

# Each system entry: (system_id, runner_fn, model, requires_env_key_or_none)
def discover_systems() -> List[Tuple[str, Callable, str, Optional[str]]]:
    systems: List[Tuple[str, Callable, str, Optional[str]]] = []

    # cogOS — always on (Ollama local, no key)
    from runners.ollama import run_ollama_once
    systems.append(("cogos-qwen2.5-3b", run_ollama_once, "qwen2.5:3b-instruct", None))
    systems.append(("cogos-qwen2.5-7b", run_ollama_once, "qwen2.5:7b-instruct", None))

    # Cloud Provider B — gated on CLOUD_B_API_KEY
    if os.environ.get("CLOUD_B_API_KEY"):
        from runners.cloud_b import run_cloud_b_once
        systems.append(("cloud-b-small", run_cloud_b_once, "llama-3.1-8b-instant", "CLOUD_B_API_KEY"))
        systems.append(("cloud-b-large", run_cloud_b_once, "llama-3.3-70b-versatile", "CLOUD_B_API_KEY"))

    # Cloud Provider A — gated on CLOUD_A_API_KEY
    if os.environ.get("CLOUD_A_API_KEY"):
        from runners.cloud_a import run_cloud_a_once
        systems.append(("cloud-a-flagship", run_cloud_a_once, "gpt-4o-2024-08-06", "CLOUD_A_API_KEY"))

    # CogOS LIVE gateway — gated on COGOS_LIVE_API_KEY. This is the
    # "audit, not trust" closer: hitting the same production endpoint
    # any customer reaches, with a customer-equivalent bearer.
    if os.environ.get("COGOS_LIVE_API_KEY"):
        from runners.cogos_live import run_cogos_live_once
        systems.append(("cogos-live-tier-b", run_cogos_live_once, "cogos-tier-b", "COGOS_LIVE_API_KEY"))
        # tier-a only included when allowed by the package; the runner
        # will surface 403 model_tier_denied as a parse failure if not.
        if os.environ.get("COGOS_LIVE_TIER_A") == "1":
            systems.append(("cogos-live-tier-a", run_cogos_live_once, "cogos-tier-a", "COGOS_LIVE_API_KEY"))

    # Optional restriction via BENCH_SYSTEMS=cogos-qwen2.5-3b,...
    bench_systems_env = os.environ.get("BENCH_SYSTEMS")
    if bench_systems_env:
        allowed = {s.strip() for s in bench_systems_env.split(",") if s.strip()}
        systems = [s for s in systems if s[0] in allowed]

    return systems


# -------- Scenario/schema loading -------------------------------------------

def load_schemas() -> Dict[str, Dict[str, Any]]:
    return {
        f.stem: json.loads(f.read_text())
        for f in sorted(SCHEMAS_DIR.glob("tier*.json"))
    }


def load_scenarios() -> Dict[str, str]:
    """Return {scenario_id: prompt_text} stripped of rubric-note comments."""
    out: Dict[str, str] = {}
    for f in sorted(PROMPTS_DIR.glob("tier*.txt")):
        text = f.read_text()
        # Strip lines beginning with '#' (rubric-note comments per SPEC).
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
        out[f.stem] = "\n".join(lines).strip()
    return out


def scenario_to_tier(scenario_id: str) -> str:
    # e.g. "tier1_scenario1" -> "tier1"
    return scenario_id.split("_")[0]


def build_user_prompt(schema: Dict[str, Any], scenario_text: str) -> str:
    return (
        f"JSON Schema:\n{json.dumps(schema, indent=2)}\n\n"
        f"Fixed reference time (treat as 'now' for any relative dates): {FAKE_NOW_ISO}\n\n"
        f"Instruction:\n{scenario_text}\n\n"
        f"Output ONLY the JSON object."
    )


# -------- Loop --------------------------------------------------------------

def _failed_record(
    *,
    system_id: str,
    model: str,
    mode: str,
    parser_mode: str,
    scenario_id: str,
    schema_id: str,
    run_index: int,
    seed: int,
    error: str,
    timestamp_iso: str,
) -> BenchRecord:
    return BenchRecord(
        system=system_id,
        model=model,
        mode=mode,
        parser_mode=parser_mode,
        scenario_id=scenario_id,
        schema_id=schema_id,
        run_index=run_index,
        seed=seed,
        raw_output="",
        parse_ok=False,
        parse_error=f"runner-exception: {error}",
        schema_ok=False,
        timestamp_iso=timestamp_iso,
        fake_now_iso=FAKE_NOW_ISO,
    )


def run() -> Path:
    schemas = load_schemas()
    scenarios = load_scenarios()
    systems = discover_systems()
    sizes = sample_sizes()

    if not systems:
        raise RuntimeError("No systems active. Check BENCH_SYSTEMS or env keys.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"

    print(f"[bench] output: {out_path}")
    print(f"[bench] systems: {[s[0] for s in systems]}")
    print(f"[bench] sample sizes: {sizes}")

    total_calls = 0
    total_records = 0
    start = time.perf_counter()

    with out_path.open("w") as fh:
        for system_id, runner_fn, model, _key in systems:
            for scenario_id, scenario_text in scenarios.items():
                tier = scenario_to_tier(scenario_id)
                schema_id = tier
                schema = schemas[schema_id]
                n = sizes[tier]
                user_prompt = build_user_prompt(schema, scenario_text)

                for mode in ("default", "best"):
                    for run_index in range(n):
                        seed = run_index
                        timestamp_iso = datetime.now(timezone.utc).isoformat()

                        try:
                            result = runner_fn(
                                mode=mode,
                                parser_mode="strict",
                                model=model,
                                system_prompt=SYSTEM_PROMPT,
                                user_prompt=user_prompt,
                                schema=schema,
                                scenario_id=scenario_id,
                                schema_id=schema_id,
                                **({"seed": seed} if "seed" in runner_fn.__code__.co_varnames else {}),
                            )
                            total_calls += 1
                            # Emit strict record.
                            rec_strict = from_runner_result(
                                result=result,
                                parser_mode="strict",
                                run_index=run_index,
                                seed=seed,
                                schema=schema,
                                timestamp_iso=timestamp_iso,
                                fake_now_iso=FAKE_NOW_ISO,
                            )
                            fh.write(rec_strict.to_jsonl_line() + "\n")
                            total_records += 1

                            # Default mode: also emit permissive parse of same raw_output.
                            if mode == "default":
                                rec_perm = from_runner_result(
                                    result=result,
                                    parser_mode="permissive",
                                    run_index=run_index,
                                    seed=seed,
                                    schema=schema,
                                    timestamp_iso=timestamp_iso,
                                    fake_now_iso=FAKE_NOW_ISO,
                                )
                                fh.write(rec_perm.to_jsonl_line() + "\n")
                                total_records += 1

                        except Exception as e:  # noqa: BLE001
                            err = f"{type(e).__name__}: {e}"
                            print(f"[bench] ERROR {system_id} {scenario_id} {mode} #{run_index}: {err}", file=sys.stderr)
                            for pm in (("strict",) if mode == "best" else ("strict", "permissive")):
                                bad = _failed_record(
                                    system_id=f"{system_id}",
                                    model=model,
                                    mode=mode,
                                    parser_mode=pm,
                                    scenario_id=scenario_id,
                                    schema_id=schema_id,
                                    run_index=run_index,
                                    seed=seed,
                                    error=err,
                                    timestamp_iso=timestamp_iso,
                                )
                                fh.write(bad.to_jsonl_line() + "\n")
                                total_records += 1

                        fh.flush()

                print(f"[bench] {system_id} / {scenario_id} done (n={n}, both modes)")

    elapsed = time.perf_counter() - start
    print(f"[bench] complete. {total_calls} HTTP calls, {total_records} records, {elapsed:.1f}s wall")
    print(f"[bench] -> {out_path}")
    return out_path


if __name__ == "__main__":
    run()
