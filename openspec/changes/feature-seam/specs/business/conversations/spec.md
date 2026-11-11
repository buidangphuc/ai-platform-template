## ADDED Requirements

### Requirement: Sample chat domain with Postgres

When `CONVERSATIONS_ENABLED` is true (settings require `DATABASE_ENABLED` and `LLM_ENABLED`), the `conversations` feature SHALL expose `POST /api/v1/conversations`, `GET /api/v1/conversations` (offset pagination via `PaginationParams`), `GET /api/v1/conversations/{id}/messages` and `POST /api/v1/conversations/{id}/messages`. Sending a message SHALL read the history, call `llm.ainvoke`, and store the user and assistant messages in one transaction. Every query SHALL be scoped to `principal.id`; another principal's conversation SHALL answer `404`.

#### Scenario: Send a message
- **WHEN** a principal posts a message to their conversation
- **THEN** the response holds the assistant reply and both messages are stored in order

#### Scenario: Foreign conversation
- **WHEN** principal B reads or posts to principal A's conversation
- **THEN** the response is `404`

#### Scenario: Failed model call
- **WHEN** the LLM call raises
- **THEN** neither message is stored

#### Scenario: Migration is reversible
- **WHEN** `alembic upgrade head` then `downgrade -1` runs on Postgres
- **THEN** both complete and the two tables are created then dropped
