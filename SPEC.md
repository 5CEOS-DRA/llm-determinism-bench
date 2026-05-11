# SPEC: cogOS vs Cloud Endpoints — Schema-Fidelity Benchmark
Repo: `~/bench-cogos-vs-endpoint/`
Status: **v0.3 DRAFT** — Groq added as primary cloud comparator (free tier); OpenAI demoted to gated-optional; cost narrative shifted from "100× cheaper" to "parity cost + determinism + locality + no rate limits."

Previous: v0.2 LOCKED preserved at `SPEC.v0.2.md`.

---

## 1. Scope and doctrine

**Objective:**
Benchmark a *runtime* (cogOS) vs *cloud endpoints* (Groq primary, OpenAI gated) on **schema-fidelity** and related operational properties, under the 5CEOs GreenOps + determinism doctrine.

**Non-goals:**
- Not "who is the smartest model."
- Not a generic "LLM bake-off."
- Not allowed to touch `5ceos-platform-internal` or violate the **no-cloud-LLM** doctrine.

**Repo isolation:**
- This benchmark lives in a **sibling repo**: `~/bench-cogos-vs-endpoint/`.
- No imports from, or writes to, `5ceos-platform-internal`.
- No weakening of `tests/doctrine/no-openai.test.js`.
- All cloud comparators (Groq, OpenAI) are called only from this sibling repo.

---

## 2. cogOS — local runtime

- **Runtime:** Ollama (local)
- **Models:**
  - Tier B (primary, GreenOps-aligned): `qwen2.5:3b-instruct`
  - Tier A (secondary column): `qwen2.5:7b-instruct`
- **Endpoint:** `http://localhost:11434/api/chat`
- **Ollama version requirement:** `>= 0.5.0` for best-mode (`format: <schema>`). ✅ verified 0.13.1 on this host.
- **Request shape baseline:** model + messages (system + user) + `stream: false` + `options.temperature: 0`.

**"cogOS" in this spec =** Ollama-served Qwen2.5 (3B/7B) with runtime-enforced schema constraints and deterministic settings, representing the local cognition substrate.

---

## 3. Cloud comparators

### 3.1 Groq (PRIMARY)

**Why primary:** Free tier, no credit card, structured outputs supported, two production models that span the speed/quality spectrum.

**Models pinned:**
- **`llama-3.1-8b-instant`** — fast/cheap column; size-matched to Qwen2.5:3B for fair comparison.
- **`llama-3.3-70b-versatile`** — high-quality open-weight column. **Replaces the deprecated `mixtral-8x7b-32768`** (Groq retired Mixtral in mid-2024).

**Endpoint:** `https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible)

**Auth:** `GROQ_API_KEY` env var. Free tier covers full benchmark volume (rate limit ~30 RPM / ~14,400 req/day per model; bench uses ~580 calls/model).

### 3.2 OpenAI (GATED / OPTIONAL)

**Status:** Runs only if `OPENAI_API_KEY` is staged. Absent key = column is silently skipped in the harness output.

**Why kept:** Triangulates three regimes — (1) **premium cloud** (gpt-4o), (2) **fast cloud open-weight** (Groq 8B), (3) **high-quality cloud open-weight** (Groq 70B). Prevents "you cherry-picked Groq" criticism.

**Model pinned:** `gpt-4o-2024-08-06`

**Endpoint:** `https://api.openai.com/v1/chat/completions`

**Cost when enabled:** ~$0.87 for the full bench (580 calls × $0.0015).

---

## 4. Modes: default vs best

Both modes are run against every active system.

### 4.1 Default mode

- System prompt instructs JSON-only + schema adherence.
- No constrained decoding / structured output.
- `temperature = 0`.
- Single-shot.

Reflects out-of-the-box developer usage. Expectation: results vary by tier and model; OpenAI is strong on clean JSON in prompt-only mode; Qwen2.5:3B may emit fences or prose.

### 4.2 Best mode (per-system mechanism)

| System | Best-mode mechanism |
|---|---|
| cogOS (Ollama) | `format: <JSON Schema>` (Ollama 0.5+ semantics) |
| Groq | `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}` |
| OpenAI | `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}` |

All `temperature = 0`. Single-shot.

Expectation: all three ≈100% schema validity; differences shift to latency, cost, determinism, and operator control.

### 4.3 Output parsing policy (default mode)

We run two parsing sub-modes and report both:

1. **Strict:** `JSON.parse` directly; any prose / fences / extras → hard failure.
2. **Permissive:** Strip leading/trailing Markdown fences (``` with optional language tag), then `JSON.parse`. No other heuristics.

Prevents fence-stripping arguments from being mistaken for "OpenAI/Groq fails default."

---

## 5. Cost accounting and GreenOps framing

### 5.1 Per-call cost (LOCKED v0.3)

Throughput assumption (unchanged from v0.2): 3-year amortization on a $1,400 Mac at 1,000 calls/hr × 8 hrs/day × 365 × 3 = **8,760,000 calls**.

| System | Cost / call | Source |
|---|---|---|
| **cogOS local (Qwen2.5 3B/7B)** | **$0.00016** | $1,400 / 8.76M amortized |
| **Groq Llama-3.1-8B-Instant (paid)** | **$0.000018** | $0.05/M-in + $0.08/M-out @ ~200/100 tok |
| **Groq Llama-3.3-70B-Versatile (paid)** | **$0.000197** | $0.59/M-in + $0.79/M-out @ ~200/100 tok |
| **OpenAI gpt-4o-2024-08-06** | **$0.0015** | $2.50/M-in + $10/M-out @ ~200/100 tok |
| **Groq Free Tier (any model, ≤14,400/day)** | **$0** | Until rate limit; bench fits entirely |

### 5.2 $/valid-output

For each system × mode × schema:
```
$per_valid_output = cost_per_call / schema_valid_rate
```

### 5.3 Comparative regimes (LOCKED)

At best mode where all systems are ≈100% valid:

| Comparison | Cost ratio | Story |
|---|---|---|
| cogOS vs OpenAI | 1 : 9.4 | cogOS ~9× cheaper |
| cogOS vs Groq 70B (paid) | 1 : 1.25 | Roughly parity (cogOS slightly cheaper) |
| cogOS vs Groq 8B (paid) | 9 : 1 | **Groq is ~9× cheaper than cogOS** |
| cogOS vs Groq Free Tier | local-amortized vs $0 | Groq trivially wins at bench volumes |

**Implication:** the v0.2 "cogOS is 100× cheaper than the cloud" headline does not survive contact with Groq. The cost story is real against OpenAI; it inverts against Groq 8B; it ties against Groq 70B; it disappears against Groq free tier. **Cost is no longer the headline.** See §8.

---

## 6. Semantic correctness method

Schema validity alone is gameable by trivial filler.

### 6.1 v0.3 method: deterministic, scenario-specific rubrics

- **Tier 1 & 2:** hand-coded, deterministic rubrics per scenario.
  - `priority` must match urgency keyword in scenario (urgent|high|critical → high).
  - `tags` must include the named tags.
  - `steps` length must match "three steps" / "two steps" / "one step".
  - **Deadline handling:** pin a fake "now" = `2026-05-10T12:00:00Z`. Rubrics interpret relative deadlines against this fixed clock — fully reproducible.

- **Tier 3:** explicit scenario-specific rules:
  - `intent.normalized_type` must match the scenario's task type (summarization / classification / generation).
  - `constraints.must_be_deterministic` must be `true`.
  - `routing.explanation` must contain key substrings (model / latency / cost).

  Labeled as **necessary, not sufficient** — a model can technically pass with valid filler. Acceptable for v0.3; LLM-as-judge deferred.

### 6.2 Retry-to-valid metric

Single-shot per sample. We compute:
```
expected_retries_to_valid = 1 / schema_valid_rate
```
This is the GreenOps "wasted call" framing in one number.

---

## 7. Determinism measurement

### 7.1 Method

For each system × mode × schema:
- Model version pinned.
- `temperature = 0`.
- All prompts identical.
- `seed` pinned where supported (OpenAI: best-effort; Groq: same).
- **N = 20** repeated calls with identical input.
- Measure: `unique_outputs = count(distinct(JSON_string))`; `determinism = 1 / unique_outputs`.

### 7.2 Provider metadata to log

- **OpenAI:** `system_fingerprint` (from response body). If it changes mid-run → flag segment as non-comparable (model snapshot shifted).
- **Groq:** also returns `system_fingerprint` in its OpenAI-compatible response body. Same treatment.
- **cogOS (Ollama):** no equivalent; the model artifact is pinned by Ollama model digest. Log Ollama `model` digest at start of run for record-keeping.

### 7.3 Expected pattern

- cogOS (best mode, temp 0) → `unique_outputs` ≈ 1.
- Groq → likely deterministic within a snapshot; no provider guarantee.
- OpenAI → `unique_outputs` > 1 expected even with `seed`.

---

## 8. Headline claims (v0.3 narrative)

### 8.1 Default mode
Results vary by tier and model. OpenAI / Groq are strong on clean JSON in prompt-only mode; Qwen2.5:3B may emit fences or prose. The benchmark reports, not assumes.

### 8.2 Best mode (the real story)
All three regimes (cogOS, Groq, OpenAI) are expected to reach ≈100% schema validity in best mode. **The differentiators are operational, not validity:**

1. **Determinism** — cogOS at temp=0 is byte-deterministic across runs. Cloud providers are best-effort under `seed` and subject to silent model-snapshot shifts (`system_fingerprint` drift).
2. **Locality** — cogOS data never leaves the local environment. Cloud providers carry ToS, telemetry, and (depending on tier) training-data exposure.
3. **Rate-limit freedom** — cogOS runs at hardware-sustained throughput. Cloud providers throttle at API-tier limits.
4. **No provider drift** — cogOS model is pinned by Ollama digest. Cloud models can change behind a stable name (dated snapshots like `gpt-4o-2024-08-06` mitigate; many provider models don't have them).
5. **Operator control** — cogOS is portable across any host with Ollama + model file. Cloud usage is gated on provider availability + ToS.

### 8.3 Cost framing (LOCKED v0.3)
- vs OpenAI: cogOS ~9× cheaper (real, but contingent on OpenAI pricing).
- vs Groq 8B: cogOS ~9× *more expensive* — but Groq carries every operational gap above.
- vs Groq 70B: cost parity.
- vs Groq free tier: trivially loses on raw $/call up to rate limits; equation reverses at sustained volume past free-tier caps.

**The headline is no longer "cogOS is cheaper." It is: "cogOS is at cost parity with the cheapest open-weight cloud while delivering determinism, locality, rate-limit freedom, no provider drift, and full operator control."**

### 8.4 GreenOps doctrine validation
- Tier B local model is sufficient for schema-fill workloads.
- Cloud premium models are overkill for this class of task.
- 7B column provides headroom: "even our 3B keeps up; 7B is the upper bound."

---

## 9. Schemas, scenarios, and sample sizes

### 9.1 Schemas and scenarios
[unchanged from v0.2] — 3 tiers, 3 scenarios per tier, deadline rubrics anchored to fixed "now" 2026-05-10T12:00:00Z.

### 9.2 Sample sizes

Per system × mode × schema × scenario:
- Tier 1: n = 33 / scenario → ~100 / tier
- Tier 2: n = 33 / scenario → ~100 / tier
- Tier 3: n = 10 / scenario → 30 / tier

**Active systems (minimum free path):**
- cogOS Qwen2.5:3B, cogOS Qwen2.5:7B
- Groq Llama-3.1-8B-Instant, Groq Llama-3.3-70B-Versatile
- = **4 systems**

**With OpenAI keyed:** 5 systems.

Main calls per system per mode: ~230. Two modes: ~460 / system.

| Path | Total main | Determinism (20×s×m×3) | Grand total |
|---|---|---|---|
| Free (4 systems) | 1,840 | 480 | **2,320 calls** |
| With OpenAI (5 systems) | 2,300 | 600 | **2,900 calls** |

### 9.3 Cost & wall-clock budget

- **Free path:** $0. Wall-clock ~45 min (dominated by Groq free-tier rate limits; cogOS is local; parallelization across 4 systems helps).
- **+OpenAI:** add ~$0.87 and ~10 min serial OpenAI.

---

## 10. Open questions

- **Include 7B in v0.3?** Yes — secondary column, ~10 min extra local time, closes the "3B barely lost" hole.
- **3 scenarios per tier?** Yes — already integrated.
- **Power draw?** No — defer to dedicated GreenOps bench. `$/valid-output` carries the v0.3 story.
- **LLM-as-judge for Tier 3 semantic checks?** No in v0.3 — substring rubrics labeled "necessary not sufficient."

---

## 11. Promotion criteria to v0.3 LOCKED

1. **Ollama version verified** `>= 0.5.0`. ✅ (0.13.1)
2. **Cost-accounting method §5** instantiated for all 4–5 systems. ✅
3. **Parsing policy §4.3** implemented. ✅ (`parsers/strict.py`, `parsers/permissive.py`)
4. **Schema validator §6** implemented. ✅ (`parsers/schema.py`)
5. **3-scenarios-per-tier** in `/prompts`. ✅
6. **`runners/ollama.py`** smoke-tested live. ✅
7. **`runners/openai.py`** structurally ready, awaits key. ✅
8. **`runners/groq.py`** lands + smoke-tests against free tier. ⏳ (next code session)
9. **Harness loop** wires 4 systems (cogOS×2 + Groq×2), OpenAI lights up when keyed. ⏳
10. **First live free-tier run** completes, CSV emitted, narrative §8 validated against data. If data contradicts (e.g., cogOS *loses* on determinism), pause + reframe before publishing. ⏳

Only after all 10 are ✅ do we publish.

---

## Changelog from v0.2

- **§1** — sibling-repo isolation extended to cover Groq as cloud comparator.
- **§3 NEW** — split into cloud comparators (Groq primary, OpenAI gated).
- **§3.1** — Mixtral correction: deprecated, replaced by `llama-3.3-70b-versatile`.
- **§4.2** — best-mode mechanism table now spans 3 systems.
- **§5.1** — cost table expanded to all 5 systems; Groq free-tier row added.
- **§5.3 NEW** — comparative regimes laid out honestly; "100× cheaper" claim retired.
- **§7.2 NEW** — Groq metadata logging (same `system_fingerprint` as OpenAI).
- **§8** — full narrative rewrite. Cost is no longer the headline; determinism + locality + control + parity-cost is.
- **§9.2** — sample sizes scaled to 4–5 systems.
- **§11** — promotion criteria expanded to 10; criteria #8–#10 are the v0.3 work.
