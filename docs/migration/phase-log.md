# DGL → platform migration — phase log (tường trình)

Running record of every migration phase: what was migrated, what was
added/changed/fixed, and what differs from legacy. Each phase ends with a
re-check against the DGL listing-generator migration plan (2026-06-02, since removed)
and [ADR](../adr/0001-dgl-listing-generator-migration.md).

Legacy source: `bds-genai-dgl` · Target: this repo · Branch: `dev_migrate_dgl`.

---

## Findings, open items & parked decisions (running ledger)

Durable notes accumulated while migrating — come back here when needed. Items
are not necessarily in scope now; they're recorded so nothing is lost.

### 0. Live A/B parity check (2026-06-02) — legacy :8000 vs new :8002
Ran both services live (legacy on :8000, migrated app on :8002 with a **real**
OpenAI model `gpt-4o-mini-2024-07-18`, Mongo `cmp_new`) via `scripts/compare_legacy.py`.
- [x] **PATH PARITY BUG found + fixed**: legacy mounts pair-address at
  `POST /api/v1/description/pair_address` (nested under `/description`), but the
  migration exposed it at top-level `POST /api/v1/pair_address` → legacy path 404'd
  on the new app. **Fix**: include `pair_address.router` with `prefix="/description"`
  in `app/api/legacy/router.py`; updated the integration test + harness to the
  legacy path. Now byte-compatible (decision D1). Verified live: both endpoints 200
  on the same paths; 3 integration tests pass.
- [x] All deterministic endpoints (usage_limit/reset/reset_all/day_limit/listing
  submit+get) — normalized-exact match. Generators (`/description`,
  `/description/pair_address`) — structural match (same envelope/data key shape;
  values differ only by LLM non-determinism).
- [ ] Only residual diff: additive `data.[].prompt_version` on `GET /listing`
  (intentional — new app stamps `PROMPT_VERSION`; legacy lacks the field).

### A. Pre-existing repo issues (NOT introduced by the migration)
> **Cleanup pass 2026-06-02 (no logic impact):** fixed the repo-drift items below
> in a dedicated chore (separate from DGL feature commits). Pyright baseline went
> **~57 → 6 errors** (the 6 remaining are DGL-code `Optional` member-access nits —
> see item below — NOT pre-existing drift).
- [x] **`.env.example` drift** — RESOLVED earlier (commit `98a21db`, `make check-env` green). The 18 "missing" keys are USED by live modules; only `DEFAULT_RATE_LIMIT_PER_MINUTE` was genuinely stale and was dropped.
- [x] **`pyrightconfig.json` stale excludes** — FIXED: excludes now point at the real `app/modules/messaging/queue/adapters/{sqs,rabbitmq}.py` + `app/modules/platform/objects/adapters/s3.py`. The ~51 optional-adapter errors are gone (57 → 6).
- [x] **`tests.factories`** — no longer flagged by pyright after the exclude fix (0 mentions).
- [x] **`README.md` stale layout** — FIXED: module tree now reflects the real `ai/ business/ messaging/ platform/` grouping; `app.modules.llm.runtime` → `app.modules.ai.llm.runtime`.
- [ ] **Local `.env` has keys not in `Settings`** (langfuse docker keys, `api_key_pepper`, …) → only bites a dotenv-file read under `extra="forbid"`; in Docker the keys arrive as OS env vars (ignored) so the container boots fine. Env-hygiene only; left as-is.
- [x] **DGL pyright errors** — RESOLVED in the DGL cleanup/refactor pass; current
  `uv run pyright` reports 0 errors.

### B. Decisions deferred / need confirmation
- [ ] **FastAPI pin**: target `<0.116` vs legacy `0.135.1`. Bump before Phase 2 (porting generator code written against 0.135)? (recommended)
- [ ] **Error-envelope parity**: happy paths use the legacy envelope; unhandled errors currently fall through to the platform error envelope (legacy `common/exception/exception_handler.py` not ported). Port it, or let the BFF normalize errors?
- [ ] **`contact_email`**: scaffold uses `str`; restore pydantic `EmailStr` (+ `email-validator` dep) in Phase 2 when the endpoint is wired.
- [ ] **`AddressVersionType=NEW`** is now inert (location mapping dropped). Keep the param for contract compatibility, or drop from the request schema?
- [ ] **Commit cadence**: Phase 0+1+2(part1) currently uncommitted on `dev_migrate_dgl`.
- [x] **LLM sampling-param pinning** — RESOLVED (Phase 4): the listing chat model is built with `init_chat_model(CHAT_MODEL, temperature/top_p + model_kwargs penalties)` from `LISTING_LLM_*`; the Langfuse tracker is attached separately (not via `ModelRouter`), so params stay pinned and tracing works.
- [x] **Langfuse** — ADOPTED (Phase 4): prompt management (`project_summary`) + tracing wired with a file fallback; ADR D3 revised.

### C. Parked improvements (deliberately NOT done — keep legacy behavior)
- [ ] Usage quota **race condition** (read-modify-write) → atomic `find_one_and_update` `$inc`.
- [ ] `PUT /day_limit` mutates **process-local settings** (not persisted, not multi-worker safe) → persist in Mongo/Redis.
- [ ] **Structured output** (replace regex parsing) → agreed **Phase 4** fast-follow.
- [ ] **Durable listing writes** (`BackgroundTasks` → outbox/tasks) → Phase 4.
- [ ] **Resilience/timeouts + cache** around external calls (GMaps/BDS) → opt-in later.
- [ ] **Idempotency** on `/description` (BFF `Idempotency-Key`) → opt-in.
- [ ] Adopt-for-free **#11 eval harness** + group C (async-tasks/idempotency/cache/resilience/audit) + pagination/RAG/gzip — parked (per "làm đến 10").

### D. Endpoint wiring convention going forward
Use this convention for any new legacy/listing endpoint. This supersedes the
earlier `app/api/legacy/deps.py` approach, which was removed after it started
collecting too much listing-specific wiring.

```text
app/api/legacy/<endpoint>.py
  -> request/response contract only
  -> FastAPI params/body/query
  -> Depends(app.modules.business.listing.providers.<provider>)
  -> calls one module service method
  -> maps result to the legacy envelope

app/modules/business/listing/providers.py
  -> FastAPI/runtime adapter for listing
  -> reads app resources/settings
  -> builds Mongo store, quota service, generators, template selection, etc.

app/modules/business/listing/services/*.py
  -> application use-case orchestration
  -> dependencies are explicit constructor args
  -> no FastAPI Request, no app.state, no global service lookup

app/modules/business/listing/stores/*.py
  -> Mongo/SQL persistence adapters owned by listing

app/modules/business/listing/integrations/*.py
  -> external API adapters owned by listing

app/modules/business/listing/generation/*.py
  -> prompt builders, generation engines, parsers, template utilities
```

When adding a new endpoint:

1. Put endpoint transport code in `app/api/legacy/<feature>.py`.
2. Put or reuse use-case orchestration in
   `app/modules/business/listing/services/`.
3. Add a provider in `app/modules/business/listing/providers.py` only when the
   endpoint needs runtime resources such as Mongo, settings, chat model, HTTP
   client, prompt provider, tracker, or quota.
4. Put DB details in `stores/`, external API details in `integrations/`, and
   prompt/model parsing details in `generation/`.
5. Keep API code thin: no generator/store/template construction in the endpoint.
6. Do not recreate `app/api/legacy/deps.py` for feature-specific dependencies.
   If another domain needs the same pattern, create that domain's own provider
   module under `app/modules/business/<domain>/`.

Minimal shape:

```python
@router.post("/new_feature")
async def new_feature(
    payload: NewFeatureRequest,
    service: NewFeatureService = Depends(get_new_feature_service),
) -> LegacyResponseModel:
    result = await service.run(payload)
    return await legacy_response.success(data=result)
```

### E. Legacy behaviors/gotchas to preserve in later phases
- [ ] **Google Maps API requires a `Referer` header** (see legacy `GMAP.md`) — load-bearing; carry verbatim in the nearby service (Phase 2).
- [ ] **BDS project API returns 301 redirects** that legacy follows (`ProjectSearch`/`ProjectLegacySearch`).
- [ ] **Project summary** uses OpenAI + Mongo cache (`MONGODB_PROJECT_COLLECTION`); route its LLM call through `ai/llm` too (Phase 2).
- [ ] **Prompt constants** (`PROMPT_TITLE`, …) + `ParamLangMap` not yet ported (Phase 2).
- [ ] **Template selection**: weighted random, `MAX_TEMPLATE_USAGE=2`, `PROB_PENALTY=0.3` (add these settings in Phase 2).
- [ ] **`insert_contact`** replaces `<contact_phone>`/`<contact_name>` placeholders (PII safety) — keep.
- [ ] **Listing token fields**: `prompt_tokens`/`completion_tokens`/`generating_time`/`llm_model_name` — Phase 2 must map langchain usage metadata → these.
- [ ] **`pair_address.py` ≈1000 lines** — refactor into focused units in Phase 3.
- [ ] Legacy **logs full request body at debug** (PII) — apply redaction when porting endpoints.

- [ ] **`/description` already uses structured output** (`response_format=Content`); port via langchain `with_structured_output(Content, include_raw=True)`, read usage from `raw.usage_metadata`.
- [ ] **`ModelRouter` fake model (`FakeListChatModel`) can't do structured output** → generator unit tests inject a stub chat model; real runs need `CHAT_MODEL` set to a tool-calling-capable model.
- [ ] **Project summary reads `prompt/project.txt`** from CWD in legacy → port that asset into the package and load by package-relative path (not `os.getcwd()`).

### F. Dropped (not migrating)
- location mapping: service + schema + `LOCATION_MAPPING_*` config + the `address_version=NEW`→old-address branch. (Per user; deprecated in legacy.)

---

## Phase 0 — Foundations (no behavior change)

- **Date:** 2026-06-02
- **Status:** ✅ Complete
- **Goal:** lay the infra + scaffold so later phases add domain logic without
  touching the platform core. Nothing wired into request handling yet.

### Added (new files)
| File | Purpose |
|---|---|
| `app/core/config/mongo.py` | `MongoSettingsMixin` (MONGO_ENABLED + URI/DB/collections). Default **disabled**. |
| `app/core/mongo.py` | `build_mongo_client` (lazy `importlib` motor import) + `check_mongo_connection`. |
| `app/modules/platform/mongo/gateway.py` | `MongoGateway` — thin async wrapper (client/db/collection), lifespan-managed. |
| `app/modules/platform/mongo/factory.py` | `build_mongo_gateway` + `MongoAddon` (open/close on `resources.mongo`). |
| `app/modules/platform/mongo/__init__.py` | Re-exports. |
| `app/api/legacy/__init__.py` | Legacy-compat surface package doc. |
| `app/api/legacy/response.py` | Byte-compatible legacy envelope: `CustomResponseCode`, `CustomResponse`, `ResponseModel`, `response_base`. |
| `app/modules/business/listing/__init__.py` | Domain package doc. |
| `app/modules/business/listing/config.py` | Ported enums + `TemplateResponse`. |
| `app/modules/business/listing/schemas.py` | Ported `Params`, `AllParams`, `PairAddressParams`, `*Response`, `RemainResponse`, `ChangeDayLimit`. |
| `app/modules/business/listing/ports.py` | Port Protocols (`DescriptionGenerator`, `NearbyProvider`, `ProjectProvider`, `UsageQuota`, `ListingStore`). |

### Changed (edited files)
| File | Delta |
|---|---|
| `app/core/config/__init__.py` | Added `MongoSettingsMixin` to `Settings` bases + import. |
| `app/bootstrap/resources.py` | Added `mongo: MongoGateway \| None` field + TYPE_CHECKING import. |
| `app/bootstrap/addons.py` | Registered `MongoAddon()` in `default_resource_addons()`. |
| `pyproject.toml` | Added `mongo = ["motor>=3.5.0,<4.0.0"]` optional extra. |
| `.env.example` | Added `MONGO_*` block (kept in sync with new Settings fields). |

### Migrated from legacy (source → new)
- `core/generator/config.py` + `core/submit/config.py` → `business/listing/config.py` (enums, behavior-frozen values).
- `core/generator/schema/*` + `core/limiter/schema/usage.py` → `business/listing/schemas.py`.
- `common/response/response_schema.py` + `response_code.py` → `app/api/legacy/response.py`.
- `common/database/db_mongo.py` (import-time singleton) → `app/modules/platform/mongo/` (lifespan-managed).

### Deltas vs legacy (intentional)
1. **Mongo is lifespan-managed** via `MongoAddon`, not an import-time singleton. Behavior-neutral; removes import-time connection.
2. **Setting renamed** `MONGODB_CONNECTION_TIMEOUT` → `MONGODB_CONNECTION_TIMEOUT_MS` (clarity). New-platform config only; never seen by API clients.
3. **Enums** use stdlib `enum.StrEnum`/`IntEnum` instead of legacy `common.enum`. Same values → same serialized output.
4. **`contact_email: EmailStr` → `str`** (TEMP). Avoids adding `email-validator` to the scaffold; restore `EmailStr` in **Phase 2** when the endpoint is wired. ⚠️ tracked.
5. **`check_price` validator** rewritten from `@classmethod(values)` nested-`if` to instance-method combined-`if` (behavior-equivalent; satisfies ruff SIM102).
6. **Not ported (deferred):** prompt-text constants + `ParamLangMap` (→ Phase 2); persistence doc models `Listing`/`User` with `bson.ObjectId` encoders (→ Phase 1, in the Mongo adapter layer).
7. **Dropped (per ADR):** location mapping — no schema/service/config ported. `city_code/district_id/ward_id/street_id` kept as **inert optional** fields for request-contract compatibility.

### Adopt-for-free (plan items 1–10)
These platform capabilities already exist in `backend`; Phase 0 adds no code for
them — new modules simply conform/plug in (typed errors, structured logging +
request_id, redaction, access-log, `/healthz`+`/readyz`, OTel wiring, graceful
shutdown + lifespan resources, ruff/pyright/pre-commit/detect-secrets,
pytest-xdist, Docker/Makefile/Alembic). The `MongoAddon` follows the existing
lifespan/addon convention; the legacy envelope will map typed `AppError`s at the
edge when routes are wired (Phase 1).

### Verification
- `ruff check .` → **clean**; `ruff format --check` → clean (199 files).
- `pytest -n auto` → **349 passed, 3 skipped** (unchanged from baseline).
- `Settings(_env_file=None, …)` → `MONGO_ENABLED=False`, `MONGODB_DATABASE=genai`, collections `user/submit/project` ✓.
- `AllParams(...)` validates; legacy `response_base.success(data=...)` → `{'code':200,'message':'OK','data':{...}}` (byte-compatible) ✓.
- `MongoAddon` registered, **inert by default** (`is_enabled→False`), friendly `RuntimeError` when `motor` extra absent ✓.

### Known issues / pre-existing (not introduced by this phase)
- **`make check-env` already drifted at baseline**: missing `RATE_LIMIT_IP_ENABLED`, `RATE_LIMIT_IP_PER_MINUTE`, `RATE_LIMIT_PRINCIPAL_ENABLED`, `RATE_LIMIT_PRINCIPAL_PER_MINUTE`, `TASKS_DISPATCH_BACKEND`, `TASKS_LEASE_SECONDS`; stale `DEFAULT_RATE_LIMIT_PER_MINUTE`. Our `MONGO_*` keys ARE in sync. Left as-is (out of scope); flagged for a separate cleanup.
- **`pyright` had 57 errors at baseline** (stale excludes in `pyrightconfig.json` pointing at pre-refactor `app/modules/queue|objects/...` paths; optional adapters unresolved). Mongo code uses `importlib` + `Any` to avoid adding new import errors. Stale excludes flagged for separate cleanup.
- The local `.env` contains many keys not in `Settings` (langfuse docker keys, `api_key_pepper`, …) so `get_settings()` against it raises under `extra="forbid"` — environmental, pre-existing; tests build settings independently.

### Re-check vs plan §4 Phase 0
- [x] `motor` optional dep + `MongoAddon` + config fields + resources wiring
- [x] Port `response_base`/`CustomResponseCode` envelope → `app/api/legacy/response.py`
- [x] Scaffold `business/listing/` (ports, schemas, config enums) — no logic
- [~] **Confirm + bump FastAPI pin** — **DEFERRED**. Target `<0.116` vs legacy `0.135.1`. Not bumped (touches whole platform + 349 tests); will revisit in Phase 2 when porting generator code written against 0.135. Needs user confirmation (§8 #1).
- [x] Adopt-for-free items 1–10 — reused existing platform facilities; new modules conform.

### Next (Phase 1)
Usage limiter (`/usage_limit/{user_id}`, `/reset`, `/reset_all`, `/day_limit`)
and listing submit/get on the Mongo adapter, behind the legacy-compat router;
integration tests against Mongo (mongomock/testcontainers).

---

## Phase 1 — Usage limiter + listing store (simple domains)

- **Date:** 2026-06-02
- **Status:** ✅ Complete
- **Goal:** port the two simplest legacy domains (usage quota + listing
  submit/get) onto the Mongo adapter, behind the legacy-compat router, with
  byte-compatible paths + envelope. No LLM yet.

### ⚠️ Correction carried into this phase
Legacy actually mounts its API under `prefix=API_V1_STR="/api/v1"` (the Phase 0
codegraph manifest had stripped the prefix). Real paths are
`/api/v1/usage_limit/{user_id}`, `/api/v1/listing/submit`, etc. — **not** root.
ADR D1 + plan §2 were corrected accordingly. Legacy mounts these **public** (the
global auth dependency is commented out), so the compat router is public too.

### Added (new files)
| File | Purpose |
|---|---|
| `app/core/config/listing.py` | `ListingSettingsMixin` — `MAX_USAGE_LIMIT_PER_USER=100`, `MAX_RESET_LIMIT_DAYS=30`. |
| `app/modules/business/listing/models.py` | `Listing`, `UsageUser` Mongo doc models (no bson; `created_date` → legacy-format string in JSON). |
| `app/modules/business/listing/services/usage.py` | `UsageService` (30-day quota), gateway-injected. |
| `app/modules/business/listing/services/listing_store.py` | `ListingStore` (create/get/last-ai). |
| `app/modules/business/listing/services/__init__.py` | Package marker. |
| `app/api/legacy/deps.py` | Per-request service resolution from `resources.mongo` (503 if absent). |
| `app/api/legacy/usage.py` | `/usage_limit/{user_id}`, `/reset/{user_id}`, `/reset_all`, `/day_limit`. |
| `app/api/legacy/listing.py` | `/listing/submit`, `/listing`. |
| `app/api/legacy/router.py` | Combines usage + listing routers (tags `Tracking`, `Listing`). |
| `tests/mongo_fake.py` | In-memory motor-collection fake (find_one/insert_one/update_one/delete_many/find().sort().limit()). |
| `tests/unit/modules/listing/test_usage_service.py` | 5 unit tests. |
| `tests/unit/modules/listing/test_listing_store.py` | 3 unit tests. |
| `tests/integration/test_legacy_dgl.py` | 5 endpoint tests (envelope, roundtrip, not-found, day_limit, mongo-disabled 404). |

### Changed (edited files)
| File | Delta |
|---|---|
| `app/core/config/__init__.py` | Added `ListingSettingsMixin` to `Settings`. |
| `app/modules/business/listing/config.py` | Added `DATETIME_FORMAT` constant. |
| `app/modules/business/listing/schemas.py` | Added `SubmitListing` (+ `StyleType` import). |
| `app/api/router.py` | Mount `legacy_router` under `/api/v1`, gated on `MONGO_ENABLED`. |
| `.env.example` | Added `MAX_USAGE_LIMIT_PER_USER`, `MAX_RESET_LIMIT_DAYS`. |

### Migrated from legacy (source → new)
- `core/limiter/service/usage.py` → `services/usage.py` · `core/limiter/model/usage.py` → `models.py::UsageUser`.
- `core/submit/service/listing.py` → `services/listing_store.py` · `core/submit/model/listing.py` → `models.py::Listing`.
- `core/limiter/api/v1/usage.py` → `app/api/legacy/usage.py` · `core/submit/api/v1/listing.py` → `app/api/legacy/listing.py`.

### Deltas vs legacy (intentional)
1. **Mongo handle injected** (lifespan `MongoGateway`) into services; no import-time singleton. Logic identical.
2. **Limits read live from `Settings`** so `PUT /day_limit` runtime override is honored (legacy mutated the module-level settings; we mutate `app.state.settings` — same process-local, non-persistent semantics).
3. **`Listing.version`** defaults to `""` (model) and is set to the platform `settings.VERSION` on submit (legacy used the app version at import). Metadata-only difference.
4. **`Listing` JSON** serializes `created_date` via a `field_serializer(when_used="json")` to guarantee the legacy `%Y-%m-%d %H:%M:%S` format under ORJSONResponse (legacy relied on `ResponseModel.json_encoders` + plain JSONResponse). Final output is byte-identical; in-Mongo storage stays a real datetime.
5. **Error envelope:** happy-path responses use the legacy envelope. Unhandled errors currently fall through to the platform error envelope (legacy `exception_handler` not ported). Tracked — revisit if the BFF needs legacy error shape.
6. **No correctness "fixes"** applied (atomic `$inc`, persisted day-limit) — parked per scope; behavior kept identical to legacy.

### Verification
- `ruff check .` → clean; `ruff format` clean.
- `pytest -n auto` → **362 passed, 3 skipped** (was 349 → +13 new tests, no regressions).
- Integration: envelope `{code,message,data}` correct; submit→get roundtrip; `created_date` is `%Y-%m-%d %H:%M:%S` (space, no `T`); `PUT /day_limit` mutates settings; **routes absent (404) when `MONGO_ENABLED=false`** → default app unaffected.

### Known issues / pre-existing (not introduced)
- `make check-env` still red from **pre-existing** drift (`RATE_LIMIT_*`, `RAG_RETRIEVE_TIMEOUT_SECONDS`, `TASKS_DISPATCH_BACKEND`, `TASKS_LEASE_SECONDS` missing; stale `DEFAULT_RATE_LIMIT_PER_MINUTE`). Earlier `tail` truncation hid the full list. Our `MONGO_*`/`MAX_*` keys are in sync. Left for a separate cleanup.

### Re-check vs plan §4 Phase 1
- [x] Usage limiter (`/usage_limit/{user_id}`, `/reset`, `/reset_all`, `/day_limit`) on Mongo adapter
- [x] Listing submit/get (`/listing/submit`, `/listing`)
- [x] Wired behind the legacy-compat router (under `/api/v1`, gated on `MONGO_ENABLED`)
- [x] Integration tests against Mongo — via an in-memory fake gateway (no network; mongomock/testcontainers not needed for this layer)

### Next (Phase 2)
`POST /description`: port enums/prompts/template-selection + nearby/project
HTTP services; build `DescriptionGenerator` on `ai/llm`; background listing
submit + usage increment; golden-output parity tests.

---

## Phase 2 — `POST /description` (IN PROGRESS — delivered in verified increments)

- **Date:** 2026-06-02
- **Why increments:** Phase 2 is ~1200+ lines (the ~600-line generator + ~370-line
  nearby + project + prompt builder + ~20 settings + the langchain structured-output
  swap + a `prompt/project.txt` asset). Landing it in verified parts keeps quality high.

### 🔎 Correction to an earlier assumption
Legacy `core/generator/service/description.py` **already uses OpenAI structured
output** — `client.beta.chat.completions.parse(..., response_format=Content)` where
`Content = {title, description, quality_score}`, then `completion.choices[0].message.parsed`
+ `insert_contact`. There is **no regex parsing** on this path. So the faithful
`ai/llm` port uses **langchain `with_structured_output(Content)`** — i.e. the
"structured output" target is already how `/description` behaves (the Phase-4
"switch to structured output" note applies to other paths, e.g. pair_address).

### Part 1 — foundation (✅ done)
Deterministic, fully unit-tested, no external/LLM deps.

| Added | Purpose |
|---|---|
| `app/modules/business/listing/utils.py` | `number_standardize`, `cvt_shorten_number`, `random_use`, `random_use_one_in_list` (verbatim from legacy `common/utils`). |
| `app/modules/business/listing/prompt.py` | `PromptSectionTemplate` + `OpenAIPromptTemplate` (`to_str`/`to_api_message`); dropped tiktoken `count_tokens`. |
| `app/modules/business/listing/templates.py` | `select_template` + `calculate_weight` (weighted template selection), made sync; defensive guard on total-weight 0. |
| `tests/unit/modules/listing/test_{utils,prompt,templates}.py` | 12 unit tests. |

Changed: `ListingSettingsMixin` += `MAX_TEMPLATE_USAGE=2`, `PROB_PENALTY=0.3`; `.env.example` synced.

**Verify:** ruff clean; `pytest` → **374 passed, 3 skipped** (+12).

### Part 2 — external services (✅ done)
| Added | Purpose |
|---|---|
| `app/core/config/generator.py` | `GeneratorSettingsMixin` — GMAP_* / BDS / PROJECT / LISTING_LLM_* / MAX_HOOK_WORDS / ASYNC_TASK_TIMEOUT. |
| `app/modules/business/listing/services/nearby.py` | Google Maps nearby search (injected duck-typed client, per-instance HEADERS, consolidated filtering). |
| `app/modules/business/listing/services/project.py` | BDS lookup (301 follow) + LLM summary (injected chat model) + Mongo cache. |
| `app/modules/business/listing/models.py::Project` | Cached project-summary model (summary fields optional). |
| `app/modules/business/listing/prompts/project.txt` | Summary prompt asset (loaded by package path, not `os.getcwd()`). |
| `tests/unit/modules/listing/test_{nearby,project}.py` | 9 tests (httpx `MockTransport` + stub chat + fake Mongo). |

Changed: `Settings` += `GeneratorSettingsMixin`; `.env.example` synced.

Deltas vs legacy: HTTP client + chat model + Mongo gateway **injected** (no
import-time singletons); httpx never imported at module top (duck-typed client)
per the platform's lazy-import convention; cookies-or-`Referer` headers built
per-instance from settings; project summary LLM runs through the `ai/llm` chat
model (plain completion → JSON); None-safe nearby score guards.

**Verify:** ruff clean; full suite **383 passed, 3 skipped** (+9).

### Part 3 — `DescriptionGenerator` on `ai/llm` (✅ done)
| Added | Purpose |
|---|---|
| `app/modules/business/listing/handlers/description.py` | `Content`/`Title`/`Description` schema + `DescriptionGenerator.agenerate` — prompt-building ported **verbatim** (3 professional templates + simple, every `random_use`/`np.random` variation, full rule/title/nearby/project/ending blocks). |
| `app/modules/business/listing/config.py::ParamLangMap` | VN key/value map for the prompt input (verbatim, `ClassVar`). |
| `tests/unit/modules/listing/test_generator.py` | 5 tests (stub chat model implementing `with_structured_output(...).ainvoke`). |

Deltas vs legacy: LLM call `client.beta.chat.completions.parse(response_format=Content)`
→ langchain `chat_model.with_structured_output(Content, include_raw=True)` (same
schema); usage mapped `usage_metadata.input/output_tokens` →
`tokens.usage.prompt_tokens/completion_tokens`; `llm_model_name` = `settings.CHAT_MODEL`;
nearby/project/chat injected; defensive `is_price_available` init (legacy could
KeyError on price≤0 non-negotiable, which validators prevent anyway).

**Verify:** ruff clean; full suite **388 passed, 3 skipped** (+5).

### Part 4 — `POST /description` endpoint + wiring (✅ done)
| Added | Purpose |
|---|---|
| `app/modules/business/listing/factory.py` | `ListingGeneratorAddon` + `build_listing_chat_model` (params pinned via `LISTING_LLM_*`, lazy langchain) + `build_listing_http_client` (lazy httpx). |
| `app/api/legacy/description.py` | `POST /api/v1/description`: `enforce_usage_limit` dep (429) → `select_template` → `agenerate` → background submit + usage increment → legacy envelope. |
| `app/api/legacy/deps.py::get_description_generator` | Assembles nearby+project+generator per-request from lifespan resources. |
| `tests/integration/test_legacy_description.py` | 2 tests (happy-path envelope + quota-exceeded 429). |

Changed: `ApplicationResources` += `listing_http_client` / `listing_chat_model`;
`ListingGeneratorAddon` registered (enabled when `MONGO_ENABLED`); legacy router
includes the description route; removed redundant `alias="platform"` (pydantic warning).

Deltas vs legacy: chat model + httpx client provisioned once in lifespan (addon)
and injected (no singletons); `UsageLimitMiddleware` → `enforce_usage_limit`
dependency raising `RateLimitError` (429 in the **platform** envelope — legacy
error-envelope parity still parked, ledger B); `BackgroundTasks` retained for the
listing write (durable outbox path is plan Phase 4).

**Verify:** ruff clean; full suite **390 passed, 3 skipped** (+2).

### Phase 2 — COMPLETE ✅
`POST /description` migrated end-to-end (Mongo + `ai/llm` structured output),
byte-compatible path + envelope, public, gated on `MONGO_ENABLED`. **+41 tests
across Phases 0–2 (349 → 390).**

### Re-check vs plan §4 Phase 2
- [x] Port enums / schemas / template selection (Part 1)
- [x] Port nearby + project HTTP services — location mapping dropped (Part 2)
- [x] `DescriptionGenerator` on `ai/llm`, legacy prompt kept verbatim, params pinned, Langfuse deferred (Part 3 + 4)
- [x] Background listing submit + usage increment (Part 4)
- [x] Golden-output parity tests (mocked chat model) (Parts 1–4)

---

## Phase 3 — `POST /pair_address` (COMPLETE ✅)

- **Date:** 2026-06-02
- Ported the ~1070-line pair-address generator (refactored), reusing Phase 2 primitives.

| Added | Purpose |
|---|---|
| `app/modules/business/listing/handlers/pair_address.py` | `PairAddressGenerator` — reuses `Content`/prompt/utils/services; pair-address specifics. |
| `app/api/legacy/pair_address.py` | `POST /api/v1/pair_address` (PairAddressParams / PairAddressDescriptionResponse); reuses the description endpoint's quota dep + submit/increment helpers. |
| `app/api/legacy/deps.py::get_pair_address_generator` | Per-request generator assembly. |
| `tests/unit/modules/listing/test_pair_address.py` + `tests/integration/test_legacy_pair_address.py` | 7 tests. |

Changed: legacy router includes the pair_address route.

Pair-address specifics ported: `{ADDRESS_PLACEHOLDER}` mechanism (LLM emits the
token → post-process `_replace_address_placeholders` injects a combined
"new (old cũ)" address via random variations), `_normalize_address_prefixes`
(lowercase đường/phường/quận…), `address_for_title` (new vs old per
`address_version`), title-length retry (≤99 chars, 2 attempts) → deterministic
`_build_fallback_title`. LLM via `with_structured_output(Content)`; usage mapped.
No new settings (reuses GMAP_* / LISTING_LLM_*).

**Verify:** ruff clean; full suite **397 passed, 3 skipped** (+7). Fixed a flaky
test assertion — one address variation legitimately omits the word "cũ".

### Re-check vs plan §4 Phase 3
- [x] Port the pair_address generator, refactored into focused units
- [x] Reuse Phase 2 services (nearby / project / templates / prompt / utils)
- [x] Parity tests (mocked chat model)

### Next (plan Phase 4)
- **Phase 4** — hardening: structured-output fast-follow for other paths, durable
  outbox listing writes, Langfuse enablement, legacy error-envelope parity,
  parked correctness fixes (atomic `$inc`, persist day_limit).

---

## Refactor — shared prompt builders (DRY)

- **Date:** 2026-06-02
- Extracted duplicated prompt-section building (role/tone/rules/title/
  description-templates/nearby/project/ending + price/area formatting) from both
  generators into `app/modules/business/listing/prompt_builders.py`. Each
  generator now composes the shared builders and keeps only its specifics
  (description: ignored-params rule; pair_address: `{ADDRESS_PLACEHOLDER}` +
  title retry/fallback + post-process). ~250 duplicated lines removed; single
  place to evolve prompt content (e.g. restore full legacy wording for parity).
- Module named `prompt_builders.py` (not `prompts.py`) to avoid colliding with
  the existing `prompts/` asset directory (project.txt) — Python would resolve
  the package over the module.
- **Verify:** behavior-preserving; ruff clean; full suite **397 passed**.

---

## Phase 4 — Langfuse prompt management + tracing (✅)

- **Date:** 2026-06-02
- **Decision change:** Langfuse is now **adopted** (ADR D3 revised from "deferred").

| Added / Changed | Purpose |
|---|---|
| `business/listing/prompt_provider.py` | `PromptProvider` port + `LangfusePromptProvider` (primary) + `FilePromptProvider` (fallback). |
| `prompts/project.txt` → `prompts/project_summary.txt` | named, fallback-able prompt asset. |
| `services/project.py` | fetches `project_summary` via the prompt provider (was reading the file directly). |
| `factory.py` | `ListingGeneratorAddon` builds a Langfuse tracker + prompt provider; resources hold `listing_tracker` / `listing_prompt_provider`. |
| `api/legacy/deps.py` | generators get `trace_config` from the tracker (tracing); `ProjectService` gets the provider. |
| `models.py::Listing` | `+ prompt_version`. |
| `handlers/{description,pair_address}.py` | `PROMPT_VERSION` constant returned + stamped on the listing. |
| `tests/.../test_prompt_provider.py` | 3 tests (file read, Langfuse-disabled→file fallback, Langfuse-available). |

How it works:
- **Static prompt** (`project_summary`) → Langfuse Prompt Management via
  `tracker.get_prompt(name, label="production")`; **file fallback** keeps
  local/test working (`LANGFUSE_ENABLED=false` → tracker raises → resolved from
  `prompts/project_summary.txt`).
- **Tracing** → generation runs with `tracker.trace_config()` callbacks, so each
  call (exact rendered prompt + token usage) appears in Langfuse when enabled.
- **Dynamic prompts** (description/pair_address) stay code-driven, versioned via
  `PROMPT_VERSION` stamped on `Listing.prompt_version` (DB tracking) + captured
  by tracing.
- Sampling params stay pinned on the chat model (`init_chat_model` +
  `LISTING_LLM_*`); the Langfuse tracker is attached separately.

**Verify:** ruff clean; check-env green; full suite **400 passed, 3 skipped** (+3).

### Remaining Phase 4 (hardening, optional)
Durable outbox listing writes (replace `BackgroundTasks`), legacy error-envelope
parity, eval scores via Langfuse, parked correctness fixes (atomic `$inc`,
persist `day_limit`).
