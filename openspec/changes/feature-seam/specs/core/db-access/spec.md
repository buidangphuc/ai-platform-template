## ADDED Requirements

### Requirement: One database access pattern

Stores SHALL receive an `async_sessionmaker` (or `MongoGateway`) through their constructor in `Feature.build`. `DbSession`, `get_db`, `MongoDep`, `get_mongo` and `get_mongo_gateway` SHALL NOT exist, and the docs SHALL describe only the constructor pattern.

#### Scenario: Removed symbols
- **WHEN** searching `app/` for `DbSession`, `get_db`, `MongoDep`, `get_mongo`
- **THEN** there are no matches
