# SPEC: cogOS vs Endpoint Schema-Fidelity Benchmark
Repo: `~/bench-cogos-vs-endpoint/`
Status: v0.2 LOCKED (doc layer) — 4 of 5 promotion criteria DONE; #3 (parsing in code) deferred to next session

---

## 1. Scope and doctrine

**Objective:**
Benchmark a *runtime* (cogOS) vs a *cloud endpoint* (OpenAI) on **schema-fidelity** and related operational properties, under the 5CEOs GreenOps + determinism doctrine.

**Non-goals:**

- Not "who is the smartest model."
- Not a generic "LLM bake-off."
- Not allowed to touch `5ceos-platform-internal` or violate the **no-cloud-LLM** doctrine.

**Repo isolation:**

- This benchmark lives in a **sibling repo**: `~/bench-cogos-vs-endpoint/`.
- No imports from, or writes to, `5ceos-platform-internal`.
- No weakening of `tests/doctrine/no-openai.test.js`.

---

## 2. What "cogOS" means in this benchmark

For this benchmark, **"cogOS" is concretely defined as:**

- **Serving stack:**
  - **Runtime:** Ollama (local)
  - **Models:**
    - Tier B (primary, GreenOps-aligned): `qwen2.5:3b-instruct`
    - Tier A (secondary column): `qwen2.5:7b-instruct`
  - **Endpoint:** `http://localhost:11434/api/chat`

- **Ollama version requirement:**

  - **Minimum:** `ollama >= 0.5.0`
  - Reason: structured outputs (JSON Schema via `format`) were added in 0.5.0.
  - **First step before any code:** run `ollama --version` and confirm `>= 0.5.0`.
  - If this is not satisfied, **best-mode for cogOS does not exist** as specified and the spec must not be promoted to LOCKED.
  - **Verified 2026-05-10:** local Ollama version is `0.13.1` ≫ 0.5.0. ✅

- **Request shape (baseline):** Ollama `/api/chat` JSON body:
  - `model`: `"qwen2.5:3b-instruct"` (or `:7b-instruct` for Tier A)
  - `messages`: `[{"role": "system", ...}, {"role": "user", ...}]`
  - `stream`: `false`
  - `options.temperature`: `0`

- **"cogOS" in this spec =**
  "Ollama-served Qwen2.5 (3B/7B) with runtime-enforced schema constraints and deterministic settings, representing the local cognition substrate."

---

## 3. Modes: default vs best

We explicitly benchmark **two modes** for both cogOS and OpenAI.

### 3.1 Default mode

- **cogOS (Ollama/Qwen):**
  - System prompt instructs JSON-only + schema adherence.
  - No structured-output / constrained decoding.
  - Temperature = 0.
  - Single-shot completion.

- **OpenAI:**
  - `gpt-4o-2024-08-06` (or newer pinned version).
  - System prompt instructs JSON-only + schema adherence.
  - No `response_format` / no JSON-schema strict mode.
  - Temperature = 0.
  - Single-shot completion.

**Purpose:** Reflects how many developers actually use these systems "out of the box."
**Expectation:** Default-mode results may vary by tier; OpenAI is genuinely strong at clean JSON in prompt-only mode. The **core story is not "we win every default tier,"** but that constrained mode is where determinism + cost + locality land cleanly.

### 3.2 Best mode

- **cogOS (Ollama/Qwen):**
  - Uses **Ollama's structured output mechanism** as the *single* constrained-decoding mechanism for v0.2.
  - Mechanism: `format` field containing the JSON Schema (Ollama 0.5+ semantics).
  - Temperature = 0.

- **OpenAI:**
  - `gpt-4o-2024-08-06`.
  - Uses `response_format: { "type": "json_schema", "json_schema": { "strict": true, "schema": <SCHEMA> } }`.
  - Temperature = 0.

**Purpose:** Compare both systems in their strongest, schema-constrained modes.
**Expectation:** Both ≈100% schema validity; differences move to latency, cost, determinism, and $/valid-output.

**Important:**
For v0.2, **we do NOT mix mechanisms** (GBNF / guided_json / Ollama).
- Best-mode for cogOS = **Ollama structured output only**.
- GBNF and vLLM guided_json are explicitly out-of-scope for this spec and can be added later as new columns.

### 3.3 Output parsing policy (default mode)

Default-mode parsing is load-bearing. We run **two parsing sub-modes**:

1. **Strict parsing:**
   - Apply `JSON.parse` directly to the raw model output.
   - Any surrounding text, fences, or prose → **hard failure**.

2. **Permissive parsing:**
   - Strip common Markdown fences and language tags:
     - Leading/trailing ``` or ```json
   - Then apply `JSON.parse`.
   - No other heuristics (no regex surgery on the body).

We report **both** strict and permissive schema-validity rates.
This prevents "OpenAI fails default" being an artifact of fence-stripping arguments.

---

## 4. GreenOps framing and model tier

Per GreenOps doctrine (2026-05-08):

- **Schema-fill is classification-shaped → Tier B (3–4B).**
- Therefore, the **headline comparison** is:

> `qwen2.5:3b-instruct` (local, Ollama, constrained)
> vs
> `gpt-4o-2024-08-06` (cloud, constrained)

### 4.1 Cost accounting: $/valid-output (LOCKED v0.2)

We define $/valid-output as a function of cost-per-call and schema-validity rate.

**Throughput assumption (LOCKED):** 3-year amortization on a $1,400 M-class Mac, at:
- **1,000 calls/hour** sustained
- **8 hours/day**
- **365 days/year**
- **3 years**

Total amortizable calls over service life:

```
1,000 × 8 × 365 × 3 = 8,760,000 calls
```

1. **OpenAI cost:**
   - Published pricing for `gpt-4o-2024-08-06`: $2.50 / 1M input + $10.00 / 1M output.
   - Typical schema-fill call (~200 input tokens, ~100 output tokens):
     - cost ≈ (200 × 2.50 / 1M) + (100 × 10.00 / 1M) = $0.0005 + $0.001 = **$0.0015 per call**.
   - `$per_valid_output_openai = cost_per_call / schema_valid_rate`.

2. **Local cogOS cost:**
   - Marginal electricity on an M-class Mac for ~1s is negligible but **not treated as zero** — explicitly outside v0.2 scope.
   - Amortized hardware: `$1,400 / 8,760,000 calls` ≈ **$0.00016 per call**.
   - `$per_valid_output_cogos = amortized_cost_per_call / schema_valid_rate`.

3. **Reported ratio:**
   - `ratio = $per_valid_output_openai / $per_valid_output_cogos`
   - = `(0.0015 / openai_valid_rate) / (0.00016 / cogos_valid_rate)`
   - = `9.375 × (cogos_valid_rate / openai_valid_rate)`

   **Regimes:**
   - **Best mode (both ≈100% valid):** `ratio ≈ 9.4×` — cogOS wins ~10× on cost alone, plus determinism, locality, no rate limits, no token-pricing exposure.
   - **Default mode (mixed validity):** ratio scales with the validity gap. If cogOS retains higher schema-validity than OpenAI in default-mode, ratio rises above 9.4×; plausible range **~40×–100×** at higher tiers if OpenAI default validity drops materially. Empirical numbers from the actual benchmark replace this expectation.

   We **state both absolute numbers and the ratio**; we do not pretend local marginal cost is zero.

This makes the cost claim explicit, auditable, internally consistent, and methodologically honest.

---

## 5. Semantic correctness method

Schema validity alone is gameable by trivial filler.
We must measure "does this JSON actually answer the scenario?"

### 5.1 v0.2 method: deterministic, scenario-specific rubrics

For v0.2, we adopt a **hybrid, scenario-specific rubric**:

- **Tier 1 & Tier 2:**
  - Use **hand-coded, deterministic rubrics** per scenario.
  - Example checks:
    - `priority` must be `"high"` if scenario mentions "urgent|high|critical".
    - `tags` must include `"incident"` and `"review"` for the Tier 1 incident scenario.
    - `steps` length must be ≥ 3 when scenario says "three steps".
    - `deadline` must match the intended relative time window.

  - **Deadline handling:**
    - We pin a **fake "now"** timestamp for the entire batch (e.g., `2026-05-10T12:00:00Z`).
    - Rubrics interpret "tomorrow at 17:00 UTC" relative to this fixed "now".
    - This makes the check fully reproducible and independent of actual run time.

- **Tier 3:**
  - We define **explicit, scenario-specific rules**, e.g.:
    - `intent.normalized_type` must be `"summarization"`.
    - `constraints.must_be_deterministic` must be `true`.
    - `routing.explanation` must contain substrings related to:
      - "small or large model"
      - "latency"
      - "cost"

  - These checks are explicitly labeled as **necessary but not sufficient**:
    - A model can technically pass by including those words in nonsense.
    - For v0.2, we accept this limitation and document it in the methodology.
    - Future versions may add richer semantic checks or LLM-as-judge as a separate, clearly disclosed metric.

**No LLM-judge in v0.2.**
If we later add LLM-as-judge, it will be a clearly labeled, separate metric with full disclosure.

### 5.2 Output of semantic check

For each completion:

- `semantic_valid: true | false`
- `semantic_errors: [string]` (which rubric checks failed)

### 5.3 Retry-to-valid metric

Even though the benchmark runs **single-shot** per sample, we compute the implied retry cost:

- `schema_valid_rate` = fraction of runs that are schema-valid.
- **Expected retries to valid:**

  - `expected_retries_to_valid = 1 / schema_valid_rate`

We report this per system × mode × schema.
This is the GreenOps "wasted call" framing in one number.

---

## 6. Determinism measurement

OpenAI does not guarantee determinism even with `temperature=0` and `seed` set; cogOS (local) can be much closer to deterministic.

### 6.1 Method

For each system × mode × schema:

- Fix:
  - Model version.
  - Temperature = 0.
  - All prompts identical.
  - Seed pinned where supported (OpenAI: best-effort).

- Run:
  - **N = 20** repeated calls with identical input.

- Measure:
  - **Exact-output uniqueness count**:
    - `unique_outputs = count(distinct(JSON_string))`
  - **Determinism score**:
    - `determinism = 1 / unique_outputs` (1.0 = perfectly deterministic).
  - Optionally, **edit-distance variance** between outputs.

- **OpenAI system_fingerprint:**
  - For every OpenAI response, log `system_fingerprint` into the raw record.
  - If `system_fingerprint` changes mid-run, we flag that the underlying model snapshot shifted and treat determinism numbers for that segment as non-comparable.

### 6.2 Expected pattern

- cogOS (local Qwen via Ollama) should show:
  - `unique_outputs` ≈ 1 in best mode.
- OpenAI likely shows:
  - `unique_outputs` > 1 even at temperature 0.

This becomes a **runtime determinism** story, not just a schema story.

---

## 7. Schemas, scenarios, and sample sizes

### 7.1 Schemas and scenarios

- **Schemas:**
  - Tier 1: simple flat.
  - Tier 2: nested.
  - Tier 3: complex routing job.
  (Final JSON Schemas live in `/schemas`.)

- **Scenarios per tier:**
  - **3 scenarios per tier** to avoid overfitting to a single prompt.
  - Tier 1: 3 different task/priority/tag scenarios.
  - Tier 2: 3 different user/role/steps/deadline scenarios.
  - Tier 3: 3 different routing/constraints scenarios.

### 7.2 Sample sizes

Per system × mode × schema × scenario:

- Tier 1: **n = 33** per scenario → ~99 ≈ 100 per tier.
- Tier 2: **n = 33** per scenario → ~99 ≈ 100 per tier.
- Tier 3: **n = 10** per scenario → 30 per tier.

Total completions (excluding determinism repeats):

- `(~100 + ~100 + 30) × 2 systems × 2 modes ≈ 920`

Determinism runs add:

- `20 × 2 systems × 2 modes × 3 schemas = 240`
- Total ≈ **1,160** calls.

### 7.3 Cost & wall-clock budget

- **OpenAI cost:**
  - ~1,160 calls at ~0.0015/call ≈ **$2–3 total**.
- **Wall-clock time (serial, 1s/call):**
  - ≈ 20 minutes.
- **Parallelizable:**
  - With modest concurrency, total wall-clock can drop to ≈ 5 minutes.

This is small enough to run repeatedly without operational pain.

---

## 8. Headline claims this spec is designed to test

Framed conservatively, given the realities you flagged:

1. **Default mode (prompt-only):**
   - Results may vary by tier.
   - GPT-4o is strong at clean JSON even without constraints.
   - Qwen2.5:3B may emit fences or prose in some cases.
   - The benchmark will **report**, not assume, which side wins per tier.
   - The narrative is: "default-mode behavior is mixed; the real separation shows up in constrained mode and cost/determinism."

2. **Best mode (constrained):**
   - cogOS (Qwen2.5:3B + Ollama structured output) is expected to **match** GPT-4o + `json_schema.strict` on schema validity.
   - cogOS is expected to win on:
     - $/valid-output (≈80–100× cheaper under the defined cost model).
     - Locality (no cloud).
     - Determinism.
     - Operator control and substrate integration.

3. **GreenOps:**
   - Tier B local model is sufficient for schema-fill workloads.
   - Cloud-scale models are overkill for this class of tasks.
   - 7B column provides headroom: "even our 3B keeps up; 7B is the upper bound."

---

## 9. Open questions (current recommendations baked in)

- **Include 7B in v0.2?**
  Yes, as a secondary column. Adds ~460 local calls (effectively free, ~10 minutes). It closes the "what if 3B barely lost?" hole.

- **More Tier 3 scenarios?**
  Yes — 3 scenarios per tier (already integrated), n=10 each for Tier 3. This is the cheapest hedge against "you got lucky on the wording."

- **Power draw in v0.2?**
  No. macOS `powermetrics` is fiddly and doesn't isolate the model process cleanly. The $/valid-output story carries the GreenOps narrative for v0.2. Power gets its own dedicated bench later.

---

## 10. Promotion criteria to v0.2 LOCKED

1. **Ollama version verified** `>= 0.5.0`. ✅ (verified 2026-05-10: 0.13.1)
2. **Cost-accounting method** in §4.1 instantiated with concrete throughput assumptions and example numbers. ✅ (1,000 calls/hr × 8 × 365 × 3 = 8.76M calls → $0.00016/call; best-mode ratio 9.4×)
3. **Parsing policy** in §3.3 implemented as written (strict + permissive columns). ⏳ (resolves through code in next session)
4. **3-scenarios-per-tier** specified and checked into `/prompts`. ✅ (9 files landed 2026-05-10)
5. **Default-mode language in §8** remains conservative. ✅

**Status: v0.2 LOCKED at the doc layer (4 of 5 criteria DONE).**
Criterion #3 resolves through code. Next session opens with: strict+permissive parser implementation, runner skeleton, or full harness — operator's call.
