# ai/rag Specification

## Purpose
How retrieved knowledge is presented to a model through the `knowledge_search` tool.

## Requirements

### Requirement: Retrieved content is delimited as untrusted data

The `knowledge_search` tool SHALL wrap each match's text in `<document id="<chunk id>"
source="retrieved">` … `</document>`, SHALL neutralise a closing document tag inside the content,
and its description SHALL state that the content is untrusted data and not instructions.

#### Scenario: Match text is wrapped
- **WHEN** the tool returns a match
- **THEN** its text starts with the document tag carrying the chunk id and ends with the closing tag

#### Scenario: Embedded closing tag cannot end the wrapper
- **WHEN** retrieved content contains a closing document tag
- **THEN** the returned text contains exactly one closing tag, at the end

### Requirement: Retrieval size is bounded

The `knowledge_search` tool SHALL reject a `top_k` greater than 20.

#### Scenario: top_k above the bound
- **WHEN** the tool input has `top_k` 21
- **THEN** input validation fails
