## Purpose

Shape of the LLM-as-judge prompt.

## ADDED Requirements

### Requirement: Judge treats graded text as data

The LLM judge prompt SHALL wrap the criteria in `<criteria>` and the graded output in `<output>`
and SHALL instruct the judge to ignore any instruction inside either tag.

#### Scenario: Attack text in the output
- **WHEN** the graded output contains instructions addressed to the judge
- **THEN** it appears only inside the `<output>` block of the prompt, after the instruction to ignore it
