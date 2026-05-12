# SPEC: llm-determinism-bench
Repo: https://github.com/5CEOS-DRA/llm-determinism-bench

## 1. Scope

Measure four properties of any chat-completions-shape LLM provider, local or cloud:

1. **Schema validity rate** — % of calls returning JSON that parses + conforms to a supplied schema
2. **Semantic validity rate** — % where the JSON also answers the scenario (hand-coded rubrics)
3. **Determinism score** — `1 / unique_outputs` over N identical-input calls at temperature 0
4. **`$ /valid-output`** — cost-per-call divided by schema-valid rate

**Non-goals:**
- Not "which model is smartest"
- Not a general LLM bake-off
- Not measuring inference latency in isolation (latency is a captured metric but not the headline)

The bench is provider-agnostic by design. It refers to cloud providers as **Cloud A** / **Cloud B** in documentation; specific endpoint URLs and model identifiers live in the runner modules where they are factual technical details.

## 2. Local runtime

- **Engine:** Ollama (local), `>= 0.5.0` required for best-mode grammar enforcement
- **Models pinned:** `qwen2.5:3b-instruct` (primary) and `qwen2.5:7b-instruct` (secondary headroom)
- **Endpoint:** `http://localhost:11434/api/chat`
- **Request shape:** model + messages + `stream: false` + `options.temperature: 0`

## 3. Cloud providers

### 3.1 Cloud Provider A
- Connects to a hosted chat-completions API (URL pinned in `runners/cloud_a.py`)
- Auth: `CLOUD_A_API_KEY`
- Default model identifier configured in `harness/loop.py`

### 3.2 Cloud Provider B
- Connects to a different hosted chat-completions API (URL pinned in `runners/cloud_b.py`)
- Auth: `CLOUD_B_API_KEY`
- Two model sizes configured (small + large)

Both providers' identities are inspectable in the runner source. The bench does not surface their brand names in documentation because the goal is to measure behavior, not promote or denigrate any specific vendor.

## 4. Modes

Both modes run against every active system.

### 4.1 Default mode
- System prompt instructs JSON-only + schema adherence
- No constrained decoding / structured output
- `temperature = 0`
- Single-shot

### 4.2 Best mode (per-system mechanism)

| System | Best-mode mechanism |
|---|---|
| Local (Ollama) | `format: <JSON Schema>` field (Ollama 0.5+ semantics) |
| Cloud A | `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}` |
| Cloud B | Same as Cloud A — chat-completions-compatible |

All `temperature = 0`. Single-shot.

### 4.3 Output parsing policy (default mode)

Two parsing sub-modes, both reported:

1. **Strict** — `JSON.parse` directly; any prose / fences / extras → hard failure
2. **Permissive** — strip leading/trailing Markdown fences (``` with optional language tag) then parse. No other heuristics

Prevents fence-stripping arguments from being mistaken for provider failures.

## 5. Cost accounting

### 5.1 Per-call cost

Throughput assumption for local: 3-year amortization on a $1,400 M-class Mac at 1,000 calls/hr × 8 hrs/day × 365 × 3 = **8,760,000 calls**.

| System | Cost / call | Source |
|---|---|---|
| Local (Qwen 2.5 3B/7B) | **$0.00016** | $1,400 / 8.76M amortized |
| Cloud B (small) paid | **$0.000018** | provider's published rate @ ~200/100 tokens |
| Cloud B (large) paid | **$0.000197** | provider's published rate @ ~200/100 tokens |
| Cloud A flagship | **$0.0015** | provider's published rate @ ~200/100 tokens |
| Cloud B free tier | **$0** | until rate limit; bench fits entirely |

Specific dollar values come from the providers' public price sheets at run time. Update the `COST_PER_CALL` dict in `harness/summarize.py` when prices change.

### 5.2 $/valid-output

For each system × mode × schema:
```
$per_valid_output = cost_per_call / schema_valid_rate
```

### 5.3 Comparative regimes

At best mode where all systems are ≈100% valid:

| Comparison | Cost ratio (illustrative) |
|---|---|
| Local vs Cloud A | 1 : 9.4 — local ~9× cheaper |
| Local vs Cloud B large | 1 : 1.25 — rough parity |
| Local vs Cloud B small | 9 : 1 — Cloud B is ~9× cheaper than local |
| Local vs Cloud B free tier | local cost vs $0 |

**Cost is not the headline.** The interesting findings are determinism, schema reliability, semantic correctness, and provider drift over time.

## 6. Semantic correctness method

Schema validity alone is gameable by trivial filler. Each scenario has a hand-coded rubric.

- **Tier 1 & 2:** deterministic checks per scenario (priority matches urgency keyword, tags include named tags, step count matches scenario language, deadline matches relative-time spec)
- **Tier 3:** explicit substring + enum checks. Labeled **necessary, not sufficient** — a model can pass with valid filler. Accepted limitation for v0.3; future versions may add LLM-as-judge as a clearly disclosed separate metric.

**Deadline handling:** pin a fixed "now" timestamp (`2026-05-10T12:00:00Z`) for the entire batch so rubrics interpret relative deadlines reproducibly.

### Retry-to-valid metric

Single-shot per sample. We compute:
```
expected_retries_to_valid = 1 / schema_valid_rate
```
Reported per system × mode × schema.

## 7. Determinism measurement

### 7.1 Method

For each system × mode × schema:
- Pin model version, `temperature = 0`, identical prompts
- `seed` pinned where supported (best-effort on cloud providers)
- **N = 20** repeated calls with identical input
- Measure `unique_outputs = count(distinct(JSON_string))`
- `determinism = 1 / unique_outputs` (1.0 = perfectly deterministic)

### 7.2 Provider metadata

- Cloud-provider responses include a `system_fingerprint` field. If it changes mid-run → flag the segment as non-comparable (model snapshot shifted)
- Local Ollama: log the model digest at run start

### 7.3 Expected pattern

- Local (best mode, temp 0) → `unique_outputs` ≈ 1
- Cloud A → typically `unique_outputs` > 1 even with `seed`
- Cloud B → likely deterministic within a snapshot; no provider guarantee

## 8. Sample sizes

Per system × mode × schema × scenario:
- Tier 1: n = 33 / scenario → ~100 / tier
- Tier 2: n = 33 / scenario → ~100 / tier
- Tier 3: n = 10 / scenario → 30 / tier

**Active systems:** auto-detected by env-key presence. Local always on; cloud providers gated on their respective API keys.

### 8.1 Cost & wall-clock budget

- **Local only:** $0. Wall-clock ~10–20 min depending on model and tier.
- **+ Cloud:** ~$2–3 of paid usage if both cloud providers run their full N. Free tier on Cloud B is sufficient for bench volumes.

## 9. Headline claims this spec is designed to test

### 9.1 Default mode
Results vary by tier and model. Some providers are strong at clean JSON in prompt-only mode; smaller open-weight models may emit fences or prose. The benchmark reports, does not assume.

### 9.2 Best mode
All regimes are expected to reach ≈100% schema validity in best mode. **Differentiators are operational, not validity:**

1. **Determinism** — local at temp=0 is byte-deterministic. Cloud providers are best-effort under `seed` and subject to silent model-snapshot shifts.
2. **Locality** — local data never leaves the host. Cloud providers carry ToS, telemetry, and (depending on tier) training-data exposure.
3. **Rate-limit freedom** — local runs at hardware-sustained throughput. Cloud providers throttle at API-tier limits.
4. **No provider drift** — local model is pinned by digest. Cloud models can change behind a stable name.
5. **Operator control** — local is portable across any host with the inference engine + model file.

### 9.3 Cost framing
- vs Cloud A: local ~9× cheaper (real, but contingent on provider pricing)
- vs Cloud B small: local ~9× more expensive — but Cloud B carries every operational gap above
- vs Cloud B large: cost parity
- vs Cloud B free tier: trivially loses on raw $/call up to rate limits; equation reverses past free-tier caps

## 10. Open questions

- 7B vs 3B local — both included as secondary column to close "what if 3B barely lost?" objections
- 3 scenarios per tier — already integrated, hedges against single-prompt overfit
- Power draw — deferred to a dedicated bench; `$ /valid-output` carries the cost narrative here

## 11. Promotion criteria

1. Ollama version `>= 0.5.0`
2. Cost-accounting method in §5 instantiated with concrete numbers per system
3. Parsing policy in §4.3 implemented (`parsers/strict.py`, `parsers/permissive.py`)
4. Schema validator in §6 implemented (`parsers/schema.py`)
5. 3 scenarios per tier in `/prompts`
6. `runners/ollama.py` smoke-tested live
7. `runners/cloud_a.py` and `runners/cloud_b.py` smoke-tested when respective keys are staged
8. Harness loop wires available systems automatically
9. First live run produces a CSV; narrative claims §9 validated against data
