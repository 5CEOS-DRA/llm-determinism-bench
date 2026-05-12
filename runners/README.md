# runners/

Single-call adapters, one per system under test. The harness (`harness/loop.py`) loops over scenarios × schemas × modes × N and accumulates the result records emitted by these adapters.

All runners share the same parser + schema path (`parsers/strict`, `parsers/permissive`, `parsers/schema`), so result records are structurally symmetric except for cloud-side runners' three additional fields (`system_fingerprint`, `prompt_tokens`, `completion_tokens`).

---

## `ollama.py` — local runtime

**Function:** `run_ollama_once(...) -> OllamaRunResult`

**Endpoint:** `http://localhost:11434/api/chat`

**Preconditions:**
- Ollama daemon running on `:11434` (`ollama serve`).
- Model pulled (`ollama pull qwen2.5:3b-instruct`).
- Ollama `>= 0.5.0` for best-mode (`format: <schema>`).

**Modes:**
- `default` — prompt-only; system + user messages only, `temperature: 0`.
- `best` — adds `format: <JSON Schema>` to the request body. Ollama 0.5+ enforces the schema at decode time.

**No auth.** No env vars required.

---

## `cloud_a.py` — hosted Cloud Provider A

**Function:** `run_cloud_a_once(...) -> CloudARunResult`

**Endpoint URL:** documented in module docstring (`runners/cloud_a.py`).

**Preconditions:**
- `CLOUD_A_API_KEY` exported in the calling shell.
- The runner raises immediately if no key is set — no silent fallback.

**Modes:**
- `default` — `messages` only, `temperature: 0`, `seed: <int>` (best-effort).
- `best` — adds `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}`.

---

## `cloud_b.py` — hosted Cloud Provider B

**Function:** `run_cloud_b_once(...) -> CloudBRunResult`

**Endpoint URL:** documented in module docstring (`runners/cloud_b.py`).

**Preconditions:**
- `CLOUD_B_API_KEY` exported. Free-tier signup typically available at the provider's website.

**Modes:** same as `cloud_a.py`.

---

## Cloud-side extra fields

Each cloud runner's result type adds three fields beyond the common 12:

- `system_fingerprint` — log per response; if it changes mid-run, the model snapshot shifted and the determinism numbers for that segment are non-comparable.
- `prompt_tokens`, `completion_tokens` — from the `usage` block. Lets the harness compute actual per-call cost.

---

## Result-record symmetry

All three runners share these fields in this order:

```
system           mode           parser_mode    model
scenario_id      schema_id      raw_output     parse_ok
parse_error      schema_ok      schema_result  latency_seconds
```

`CloudARunResult` and `CloudBRunResult` append:

```
system_fingerprint    prompt_tokens    completion_tokens
```
