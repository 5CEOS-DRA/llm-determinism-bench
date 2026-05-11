"""
Bench summary / CSV emitter.

Reads a results JSONL (or all of them, latest first) and computes the metrics
called for in SPEC v0.3:
- schema_valid_rate per (system × mode × parser × tier)
- expected_retries_to_valid = 1 / schema_valid_rate
- median latency
- mean prompt + completion tokens (cloud only)
- $/valid-output using the LOCKED cost table from §5.1
- error-category breakdowns

Emits a CSV next to the input JSONL and prints a tight summary table.

Usage:
    python -m harness.summarize                       # latest JSONL
    python -m harness.summarize <path-to-jsonl>       # specific file
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from harness.rubrics import evaluate as evaluate_rubric
from parsers.permissive import parse_permissive
from parsers.strict import parse_strict

from harness.rubrics import evaluate as evaluate_rubric
from parsers.permissive import parse_permissive
from parsers.strict import parse_strict

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "raw"
SUMMARY_DIR = REPO_ROOT / "results" / "summary"


# SPEC v0.3 §5.1 LOCKED cost-per-call table, keyed by `model` field (USD).
COST_PER_CALL: Dict[str, float] = {
    # local amortized (Mac mini $1,400 / 8.76M calls)
    "qwen2.5:3b-instruct": 0.00016,
    "qwen2.5:7b-instruct": 0.00016,
    # Groq paid pricing (free tier = $0; we report paid as the projection)
    "llama-3.1-8b-instant": 0.000018,
    "llama-3.3-70b-versatile": 0.000197,
    # OpenAI
    "gpt-4o-2024-08-06": 0.0015,
}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _bucket(rec: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (rec["system"], rec["mode"], rec["parser_mode"], rec["schema_id"])


def _semantic_ok(rec: Dict[str, Any]) -> bool:
    """Re-parse raw_output and apply scenario rubric. Only meaningful if schema_ok."""
    if not rec.get("schema_ok"):
        return False
    parser = parse_strict if rec["parser_mode"] == "strict" else parse_permissive
    parsed = parser(rec["raw_output"])
    if not parsed.ok:
        return False
    return evaluate_rubric(rec["scenario_id"], parsed.value).ok


def summarize(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in recs:
        groups[_bucket(r)].append(r)

    rows: List[Dict[str, Any]] = []
    for (system, mode, parser_mode, tier), g in sorted(groups.items()):
        n = len(g)
        parse_ok = sum(1 for r in g if r["parse_ok"])
        schema_ok = sum(1 for r in g if r["schema_ok"])
        semantic_ok = sum(1 for r in g if _semantic_ok(r))
        schema_valid_rate = schema_ok / n if n else 0.0
        semantic_valid_rate = semantic_ok / n if n else 0.0
        retries = (1.0 / schema_valid_rate) if schema_valid_rate > 0 else float("inf")

        lats = [r["latency_seconds"] for r in g if r["latency_seconds"] > 0]
        # Default-mode strict + permissive share an HTTP call; latency is the
        # same for both rows, so we don't double-count by deduping on
        # (run_index, scenario_id) at this level — the rows are intentional.
        median_latency = statistics.median(lats) if lats else 0.0

        prompt_toks = [r["prompt_tokens"] for r in g if r["prompt_tokens"] is not None]
        completion_toks = [r["completion_tokens"] for r in g if r["completion_tokens"] is not None]
        mean_in = statistics.mean(prompt_toks) if prompt_toks else None
        mean_out = statistics.mean(completion_toks) if completion_toks else None

        # Cost-per-call keyed by model name (always present on the record).
        model_in_group = g[0]["model"]
        cost_per_call = COST_PER_CALL.get(model_in_group)
        dollars_per_valid = (cost_per_call / schema_valid_rate) if (cost_per_call and schema_valid_rate > 0) else None

        # Semantic correctness via scenario-specific rubrics (SPEC §6.1).
        # Only runs on records where schema_ok=True; otherwise contributes 0.
        semantic_ok = 0
        for r in g:
            if not r["schema_ok"]:
                continue
            parser = parse_strict if r["parser_mode"] == "strict" else parse_permissive
            parsed = parser(r["raw_output"])
            if not parsed.ok:
                continue
            rr = evaluate_rubric(r["scenario_id"], parsed.value)
            if rr.ok:
                semantic_ok += 1
        semantic_valid_rate = semantic_ok / n if n else 0.0
        semantic_given_schema = (semantic_ok / schema_ok) if schema_ok else 0.0

        # Error category tallies (records where schema failed).
        extras = sum(len(r.get("extra_fields") or []) for r in g)
        missing = sum(len(r.get("missing_required") or []) for r in g)
        enums = sum(len(r.get("enum_violations") or []) for r in g)
        formats = sum(len(r.get("format_violations") or []) for r in g)
        others = sum(len(r.get("other_errors") or []) for r in g)

        rows.append({
            "system": system,
            "mode": mode,
            "parser_mode": parser_mode,
            "tier": tier,
            "n": n,
            "parse_ok_rate": round(parse_ok / n, 4) if n else 0.0,
            "schema_valid_rate": round(schema_valid_rate, 4),
            "semantic_valid_rate": round(semantic_valid_rate, 4),
            "expected_retries_to_valid": (round(retries, 3) if retries != float("inf") else None),
            "median_latency_s": round(median_latency, 3),
            "mean_prompt_tokens": round(mean_in, 1) if mean_in is not None else None,
            "mean_completion_tokens": round(mean_out, 1) if mean_out is not None else None,
            "cost_per_call_usd": cost_per_call,
            "dollars_per_valid_output": (round(dollars_per_valid, 8) if dollars_per_valid is not None else None),
            "err_extra_fields": extras,
            "err_missing_required": missing,
            "err_enum_violations": enums,
            "err_format_violations": formats,
            "err_other": others,
        })

    return rows


def print_table(rows: List[Dict[str, Any]]) -> None:
    headers = [
        ("system", 24), ("mode", 8), ("parser_mode", 12), ("tier", 6),
        ("n", 4), ("schema_valid_rate", 18), ("semantic_valid_rate", 20),
        ("expected_retries_to_valid", 26), ("median_latency_s", 17),
        ("dollars_per_valid_output", 25),
    ]
    line = " ".join(f"{h:>{w}}" for h, w in headers)
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = []
        for h, w in headers:
            v = r.get(h)
            if v is None:
                cells.append(f"{'-':>{w}}")
            elif isinstance(v, float):
                cells.append(f"{v:>{w}.4f}")
            else:
                cells.append(f"{str(v):>{w}}")
        print(" ".join(cells))


def main(argv: List[str]) -> int:
    if len(argv) >= 2:
        path = Path(argv[1])
    else:
        candidates = sorted(RESULTS_DIR.glob("run_*.jsonl"))
        if not candidates:
            print("no results JSONL found in results/raw/", file=sys.stderr)
            return 1
        path = candidates[-1]

    recs = _load_jsonl(path)
    rows = summarize(recs)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    out = SUMMARY_DIR / (path.stem + ".csv")
    with out.open("w", newline="") as fh:
        if rows:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    print(f"[summarize] input: {path}")
    print(f"[summarize] records: {len(recs)}")
    print(f"[summarize] rows: {len(rows)}")
    print(f"[summarize] csv: {out}\n")
    print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
