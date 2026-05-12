# llm-determinism-bench

**A reproducible benchmark for measuring determinism, schema-validity, and `$ /valid-output` across LLM providers — local and cloud.**

Point this at any provider you have credentials for. It fires the same prompts N times against the same schemas, then tells you:

1. **Schema validity rate** — how often the model returned JSON that parses + conforms
2. **Semantic validity rate** — did it actually answer the scenario (vs. emit valid filler)
3. **Determinism score** — how many unique outputs across N identical-input calls
4. **`$ /valid-output`** — cost-per-successful-call at the provider's pricing

Most "structured output" benchmarks measure model quality. This one measures **runtime trustworthiness** — the part you care about if you're shipping LLM-backed features to production.

## Why this exists

Every cloud LLM provider claims their structured-output mode is reliable and their `temperature=0` is deterministic. Most of those claims don't survive a re-run.

I built this to find out where each provider actually stands. It's open so anyone can attack the methodology, re-run with their own credentials, and post results.

## 60-second quick start

```bash
git clone https://github.com/5CEOS-DRA/llm-determinism-bench.git
cd llm-determinism-bench

# Use system Python 3.9+ (Homebrew Python on macOS may have pyexpat issues —
# /usr/bin/python3 is fine for this).
/usr/bin/python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run against whatever you have credentials for.
# Local Ollama needs nothing; cloud providers need an API key.
export CLOUD_A_API_KEY=...           # optional
export CLOUD_B_API_KEY=...           # optional

# Tiny sample run (n=1 per scenario, ~30s if Ollama is running):
BENCH_N1=1 BENCH_N2=1 BENCH_N3=1 python -m harness.loop

# Summary CSV:
python -m harness.summarize
```

You'll see something like:

```
                  system     mode  parser   tier  n  schema_valid  semantic_valid  $/valid_output
cogos-ollama-qwen2.5:3b  default  strict  tier1  1        1.0000          1.0000          0.0002
cogos-ollama-qwen2.5:3b     best  strict  tier1  1        1.0000          1.0000          0.0002
              cloud-a-…  default  strict  tier1  1        ...             ...             ...
       …
```

Each provider's actual identity is documented in its runner module's docstring (e.g. `runners/cloud_a.py`). The bench measures behavior, not brands — the abstraction lets you publish comparative results without naming who underperformed.

## What the bench actually does

1. **Three schema tiers** — flat (3 fields), nested (operator+task+deadline), complex routing (8 fields, 4 enums, nested constraints)
2. **Three scenarios per tier** to defuse "you got lucky on the prompt" objections
3. **Two modes per system**:
   - **default** — system prompt only, no constrained decoding
   - **best** — provider's strongest structured-output mode (Ollama `format`, cloud providers' `response_format: json_schema strict`)
4. **Two parsing sub-modes** on default-mode output:
   - **strict** — `json.loads` directly; fences or prose = fail
   - **permissive** — strip Markdown fences, then parse
5. **Hand-coded semantic rubrics** — schema validity isn't enough; we check the parsed JSON actually answers the scenario (e.g. `priority` matches urgency wording, `deadline` matches the relative time the scenario asked for)
6. **`$ /valid-output`** — cost-per-call ÷ schema-valid-rate, by provider

Full methodology, sample sizes, and decision log: [`SPEC.md`](SPEC.md).

## What's locked, what's open

- **Locked**: schemas, scenarios, parsers, rubrics, sample sizes. Don't tweak these per-run — that's how benchmarks become unfalsifiable.
- **Open**: which provider, which model, how many trials (via env vars).

Pull requests adding new providers are welcome. The runner shape is in `runners/*.py`.

## Provider-side prerequisites

| Provider class | What you need |
|---|---|
| **Local (Ollama)** | `ollama serve` running; `ollama pull qwen2.5:3b-instruct` (and 7b if you want Tier A). Version `0.5+` required for best-mode `format`-field grammar enforcement |
| **Cloud Provider A** | `CLOUD_A_API_KEY=…` env var. Default model pinned in `runners/cloud_a.py` |
| **Cloud Provider B** | `CLOUD_B_API_KEY=…` env var. Default models pinned in `runners/cloud_b.py` |

If a provider's key is missing, that column is silently skipped — the bench will still run against whatever you have.

## Repo layout

```
parsers/
  strict.py       # JSON.parse directly; surrounding text = hard fail
  permissive.py   # strip Markdown fences, then delegate to strict
  schema.py       # JSON Schema 2020-12 via jsonschema (Draft 2020-12)
runners/
  ollama.py       # POST /api/chat (Ollama 0.5+)
  cloud_a.py      # POST /v1/chat/completions to a hosted provider (URL in module docstring)
  cloud_b.py      # POST /v1/chat/completions to a hosted provider (URL in module docstring)
schemas/
  tier1.json      # flat
  tier2.json      # nested w/ date-time + role enum
  tier3.json      # complex routing job
prompts/
  tier{1,2,3}_scenario{1,2,3}.txt
harness/
  loop.py         # main: system × mode × scenario × n → JSONL
  record.py       # unified BenchRecord shape
  rubrics.py      # scenario-specific semantic checks
  summarize.py    # JSONL → CSV with schema_valid_rate, semantic_valid_rate, $/valid-output
SPEC.md           # full methodology
```

## Honest disclosure

This bench was built alongside [**cogos-api**](https://github.com/5CEOS-DRA/cogos-api) — a deterministic, schema-locked, chat-completions-compatible gateway for local LLMs. The author has a financial interest in the local runtime scoring well.

That's *exactly* why the methodology is open, the rubrics are hand-coded and visible, the schemas are committed, and every prompt is in the repo. If the bench is unfair, the PR to fix it is welcome.

## Contributing a new provider

Drop a file in `runners/yourprovider.py` matching the `runners/cloud_a.py` shape:
- Accept `mode` (`default` | `best`), `parser_mode`, model, prompts, schema
- Return a dataclass with the 12 common fields (see `runners/README.md`)
- Add to `harness/loop.py`'s `discover_systems()` with an env-key gate

Open a PR. Tests live in the runner module itself; the harness picks it up automatically once env keys are set.

## License

MIT. Use it, fork it, run it against your stack, post the numbers.

## Author

Built by [Denny Adams](https://5ceos-dra.github.io) at 5CEOS. Reach out via the blog if you want to discuss methodology or commission a benchmark for a specific workload shape.
