# Architecture Reference

## Layer Boundaries

Use this repository as a template, not a plugin platform. New apps clone the
template and wire their own product services.

### API Layer

Location: `app/api`

Responsibilities:

- Own route paths, request parsing, query/path/body parameters, response models/envelopes, auth dependencies.
- Call one business service method per endpoint when possible.
- Preserve legacy contracts during migration: path, method, query names, body shape, envelope, and status behavior.

Not allowed:

- Build stores, DB clients, HTTP clients, quota adapters, LLMs, or generators inside endpoint functions.
- Put business workflow decisions in the transport layer.

Dependency adapters:

- Put API-specific dependency adapters under the owning API surface, for example `app/api/legacy/listing_dependencies.py` or `app/api/v1/<surface>/dependencies.py`.
- Avoid generic `app/api/deps.py` files that become unrelated wiring dumps.

### Bootstrap Layer

Location: `app/bootstrap`

Responsibilities:

- Open lifecycle-owned platform resources.
- Compose application services from already-open platform resources.
- Register composed services in `ApplicationResources.services`.
- Close resources in reverse lifecycle order.

Important anchors:

- `app/bootstrap/resources.py`: `ApplicationResources`, open/close lifecycle.
- `app/bootstrap/addons.py`: `BootstrapAddon` protocol and default addon order.
- `app/bootstrap/state.py`: typed resource helpers such as `get_service_resource(...)`.

Use this layer when a service needs app-lifetime dependencies such as shared HTTP clients, LLM instances, Mongo gateway, quota service, task service, cache, object storage, or webhook dispatcher.

### Platform Modules

Location: `app/modules/platform`

Responsibilities:

- Reusable cross-product capabilities and backend adapters.
- Factories choose concrete backends from settings.
- Adapters implement one backend only.

Examples:

- Quota service -> memory/postgres/mongo stores.
- Mongo gateway -> lifecycle-managed Mongo access.
- Cache, objects, idempotency, rate limit, identity.

Rule:

```text
factory chooses implementation
adapter implements one stack
service consumes interface/capability
```

### Business Modules

Location: `app/modules/business`

Responsibilities:

- Domain/product services, schemas, models, stores, integrations, and generation logic.
- Business services receive explicit dependencies in constructors.
- Stores own collection/table details.
- Integrations own external API details.
- AI generation owns prompt building and model parsing.

Not allowed:

- Business service reads FastAPI `Request`.
- Business service reads `app.state`.
- Business module opens app-lifetime runtime resources directly.

## Adding A New Business Service

1. Create service logic under `app/modules/business/<domain>/services`.
2. Add schemas/types/models/stores/integrations under the same business domain as needed.
3. Decide whether dependencies are request-scoped or app-lifetime:
   - Request-scoped: use existing FastAPI dependency or session boundary.
   - App-lifetime: wire in `app/bootstrap` and register in `ApplicationResources.services`.
4. Add an API dependency adapter under the route surface.
5. Endpoint calls the service and preserves its response contract.
6. Add tests:
   - unit service test for orchestration and failure modes
   - adapter/bootstrap test if service is registered in `ApplicationResources.services`
   - integration test for public endpoint contract

## Adding A New Endpoint

Do not touch bootstrap when the service already has the dependencies it needs.

Flow:

```text
API endpoint
  -> dependency adapter retrieves service
  -> service.method(...)
  -> response
```

Touch bootstrap only if the endpoint introduces a new app-level service or lifecycle-owned dependency.

## Legacy/DGL Migration

During migration, keep legacy transport contracts stable. Improve internals only:

```text
legacy endpoint path stays the same
  -> API calls service
  -> service owns business flow
  -> platform capabilities provide shared infrastructure
```

Do not force legacy endpoints into the template `/v1/completions` pattern unless the user explicitly asks for a new endpoint. The completions surface is a scaffold pattern, not a replacement for migrated legacy contracts.

## Codegraph Checklist

Before changing architecture:

1. `codegraph_context` the task.
2. Identify entrypoints and related symbols.
3. If changing a shared symbol, use `codegraph_impact`.
4. If debugging a flow, use `codegraph_trace`.
5. Verify stale codegraph files by direct reads.
6. Keep final edits scoped to the discovered boundary.
