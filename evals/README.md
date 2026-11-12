# Eval datasets

`completions_smoke.jsonl` grades the completions surface **contract-level**.
The gate builds the `CompletionService` the app itself composes (`open_runtime`
with the default addons and features): with `LLM_ENABLED=false` that is the
built-in `EchoCompletionHandler`, so `make eval` runs hermetically on a fresh
fork; with `LLM_ENABLED=true` it is the model-backed handler, so the gate grades
what production serves (set `CHAT_MODEL`, and keep the dataset's expectations
valid for that model). Case format:

```json
{"id": "...", "input": {"messages": [...]}, "expected": "...", "metadata": {"evaluator": "exact|contains|judge"}}
```

- `exact` / `contains` — deterministic, always run (these gate CI).
- `judge` — LLM-as-judge; runs only when `JUDGE_CHAT_MODEL` is set (and the
  `[ai]` extra installed); otherwise the case is **skipped**, keeping CI
  hermetic. `expected` holds the grading criteria text.
- Any other `metadata.evaluator` value fails the gate, naming the case id
  and the value, before any case is scored.

## Point it at your product

1. Copy `evals/completions_smoke.jsonl` to `evals/<your-domain>.jsonl` and write real cases.
2. Register your handler in the completions feature (`handler_factory`); the
   gate picks it up because it composes services like the app does.
3. Gate: `python -m scripts.run_eval --cases evals/<file>.jsonl --min-score 0.8`
   exits non-zero below the threshold — wire it into CI once your cases are in.
