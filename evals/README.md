# Eval datasets

`completions_smoke.jsonl` grades the completions surface **contract-level**
against the built-in `EchoCompletionHandler`, so `make eval` runs out of the
box on a fresh fork. Case format:

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

1. Copy this file to `evals/<your-domain>.jsonl` and write real cases.
2. In `scripts/run_eval.py`, swap the target: build your handler/service and
   return its output for `case.input`.
3. Gate: `python -m scripts.run_eval --cases evals/<file>.jsonl --min-score 0.8`
   exits non-zero below the threshold — wire it into CI once your cases are in.
