## 1. Business service composed in lifespan (step 1)

- [x] 1.1 Rename `CompletionPipeline` → `CompletionService` (owns: business/completions/service.py, tests/unit/modules/test_completion_service.py); verify unit tests pass
- [x] 1.2 Add `app/bootstrap/services.py` (handler factory type, default echo factory, `compose_business_services`) and call it in lifespan (owns: bootstrap/{services,application}.py); verify `test_lifespan_composes_completion_service_from_handler_factory`
- [x] 1.3 `ApplicationResources.completion_service` typed field, `TaskServices` group, drop `services` registry (owns: bootstrap/{resources,state}.py); verify `test_get_task_services_*`
- [x] 1.4 Mount task routes only when `TASKS_ENABLED`; views read `get_app_resources(request.app)`; delete `completions/dependencies.py` (owns: app/api/**); verify `test_task_routes_mount_only_when_tasks_enabled`, `test_task_routes_are_not_mounted_when_tasks_disabled`
- [x] 1.5 Tests run lifespan via `api_client_for` (owns: tests/{conftest,factories}.py + affected tests); verify full pytest
- [x] 1.6 Update skill docs, README.md, TEMPLATE_GUIDE.md; verify `rg "CompletionPipeline|get_service_resource|completion_handler="` only hits historical docs

## 2. Single resource owner (step 2)

- [x] 2.1 `open_application_resources` (async CM on `AsyncExitStack`) + `open_runtime` in `bootstrap/services.py`, shared by API lifespan and worker; addon `open/close` drop the unused `app` param; delete `WorkerResources`/`_worker_needs_*` (fixes outbox + non-postgres store crash); verify `test_worker_context_uses_the_same_handler_factory_as_the_api`, `test_worker_opens_outbox_dispatch_with_non_postgres_task_store`, `test_failed_open_closes_what_was_already_opened`
- [x] 2.2 Outbox store built once: tasks open after addons and reuse `OutboxAddon`'s store; verify `test_outbox_store_is_built_once_and_shared_with_dispatcher`
- [ ] 2.3 Health checks registered at open time (deferred: `build_health_service` derives checks from opened resources; low value)

## 3. Addons and factories (step 3, parallel per addon)

- [x] 3.1 Move addon classes into `app/bootstrap/addons/<name>.py` (protocol + registry in `addons/base.py`); factories no longer import bootstrap or FastAPI; verify `rg "app.bootstrap.resources|fastapi" app/modules/*/*/factory.py` is empty
- [x] 3.2 Cross-setting "X requires Y" rules live in `@model_validator`s on `MessagingSettingsMixin` and `PlatformSettingsMixin` (fire at Settings construction); `validate_core_resource_requirements` and addon-level checks removed; verify `tests/unit/core/test_config_{messaging,platform}_rules.py`
- [x] 3.3 `QuotaAddon` awaits `MongoQuotaStore.ensure_indexes()` at open; verify `test_quota_addon_ensures_mongo_indexes_when_opening`
- [x] 3.4 Factories take required dependencies (per-backend builders); narrowing of Optional resources goes through one helper `resources.opened()`; verify `rg "is None" app/modules/*/*/factory.py` empty
- [x] 3.5 Addon contract is `open(resources, settings, stack)`: each addon pushes the close of what it built onto the exit stack; `close` methods, `= None` resets and `is not None` guards are gone; verify `test_addons_close_in_reverse_order`, `test_failed_open_closes_what_was_already_opened`
