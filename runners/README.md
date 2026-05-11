# runners/

Single-call adapters for each system under test. The harness (not yet
built) loops over scenarios × schemas × modes × N and accumulates the
result records emitted here.

Both runners share the same parser + schema path (`parsers/strict`,
`parsers/permissive`, `parsers/schema`), so result records are
structurally symmetric except for OpenAI's three additional fields.

---

## `ollama.py` — cogOS side

**Function:** `run_ollama_once(...) -> OllamaRunResult`

**Endpoint:** `http://localhost:11434/api/chat`

**Models (per SPEC §2):**
- `qwen2.5:3b-instruct` (Tier B, primary)
- `qwen2.5:7b-instruct` (Tier A, secondary column)

**Preconditions:**
- Ollama daemon running on `:11434` (`ollama serve`).
- Model pulled (`ollama pull qwen2.5:3b-instruct`).
- Ollama `>= 0.5.0` for best-mode (`format: <schema>`). Verified 0.13.1 on this host.

**Modes:**
- `default` — prompt-only; system + user messages only, `temperature: 0`.
- `best` — adds `format: <JSON Schema>` to the request body. Ollama 0.5+ enforces the schema at decode time.

**No auth.** No env vars required.

---

## `openai.py` — endpoint side

**Function:** `run_openai_once(...) -> OpenAIRunResult`

**Endpoint:** `https://api.openai.com/v1/chat/completions`

**Model (per SPEC §3):** `gpt-4o-2024-08-06` (pinned).

**Preconditions:**
- `OPENAI_API_KEY` exported in the calling shell.
  The runner raises `RuntimeError("OPENAI_API_KEY not set...")` immediately
  if it's missing — no silent fallback to a different provider.

**Modes:**
- `default` — `messages` only, `temperature: 0`, `seed: <int>` (best-effort).
- `best` — adds `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}`.

**Extra fields captured in `OpenAIRunResult` (vs Ollama):**
- `system_fingerprint` — SPEC §6.1: log per response; flag if it changes mid-run (model snapshot shifted, determinism numbers for that segment are non-comparable).
- `prompt_tokens`, `completion_tokens` — from `usage`. Lets the harness compute actual per-call cost instead of the SPEC §4.1 typical estimate ($0.0015).

---

## Result-record symmetry

Both dataclasses share these fields (in this order):

```
system           mode           parser_mode    model
scenario_id      schema_id      raw_output     parse_ok
parse_error      schema_ok      schema_result  latency_seconds
```

`OpenAIRunResult` then appends:

```
system_fingerprint    prompt_tokens    completion_tokens
```

A future `RunResult` union or protocol can fold both — not v0.2 scope.

---

## Doctrine

This sibling repo (`~/bench-cogos-vs-endpoint/`) is intentionally
isolated from `5ceos-platform-internal`. The platform's no-cloud-LLM
doctrine (`tests/doctrine/no-openai.test.js`) does not apply here —
the whole point of this repo is to *compare against* the cloud
endpoint, which is exactly why it lives in its own tree with no
imports across the boundary.
