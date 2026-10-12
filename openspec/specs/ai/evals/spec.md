# ai/evals Specification

## Purpose
The eval gate's LLM-as-judge: prompt shape, isolation of graded text, and separation from the production model.

## Requirements

### Requirement: Judge treats graded text as data

The LLM judge prompt SHALL wrap the criteria in `<criteria>` and the graded output in `<output>`
and SHALL instruct the judge to ignore any instruction inside either tag.

#### Scenario: Attack text in the output
- **WHEN** the graded output contains instructions addressed to the judge
- **THEN** it appears only inside the `<output>` block of the prompt, after the instruction to ignore it
