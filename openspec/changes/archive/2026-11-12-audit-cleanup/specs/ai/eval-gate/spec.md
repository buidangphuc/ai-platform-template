## ADDED Requirements

### Requirement: One eval loop

`scripts/run_eval.py` SHALL score cases through `run_eval_cases`; it SHALL NOT contain its own loop over cases. `run_eval_cases(cases, *, target, evaluators, tracker=None, timeout=None)` SHALL accept `evaluators` as a sequence (applied to every case) or as a callable `EvalCase -> Sequence[Evaluator]`. A case whose evaluator sequence is empty SHALL be skipped: the target is not called and the case is counted in `EvalReport.skipped_cases`.

#### Scenario: Gate output is unchanged
- **WHEN** `python -m scripts.run_eval --min-score 0.8` runs on `evals/completions_smoke.jsonl` with `.env.example`
- **THEN** it exits 0 and prints one JSON object with exactly the keys `cases`, `scored`, `passed`, `skipped_judge`, `pass_rate`, `min_score`, `failures`, with the same values as before this change

#### Scenario: Threshold fails the gate
- **WHEN** `--min-score` is above the achieved pass rate
- **THEN** the exit code is non-zero

#### Scenario: Judge case without a judge model
- **WHEN** a case has `metadata.evaluator` `judge` and `JUDGE_CHAT_MODEL` is empty
- **THEN** the case is skipped, the target is not called for it, and it is counted in `skipped_judge`

#### Scenario: No scored case
- **WHEN** every case is skipped
- **THEN** `pass_rate` is 0.0

### Requirement: Unknown evaluator fails the gate

A case whose `metadata.evaluator` is not one of `exact`, `contains`, `judge` SHALL make the gate exit non-zero with a message naming the case id and the value, before any case is scored.

#### Scenario: Mistyped evaluator
- **WHEN** a dataset contains a case with `metadata.evaluator` `contain`
- **THEN** the gate exits non-zero and the message contains the case id and `contain`

### Requirement: Report carries the gate numbers

`EvalReport` SHALL expose `total_cases`, `total_scores`, `passed_scores`, `skipped_cases`, `pass_rate` (`passed_scores / total_scores`, 0.0 when there are no scores) and `failures` (one string per failed score: `"<case id> [<score name>] <comment>"`).

#### Scenario: Mixed results
- **WHEN** a report holds one passed score, one failed score and one skipped case
- **THEN** `pass_rate` is 0.5, `skipped_cases` is 1 and `failures` has one entry
