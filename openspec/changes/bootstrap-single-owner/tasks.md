## 1. Business service composed in lifespan (step 1)

- [x] 1.1 Rename `CompletionPipeline` → `CompletionService` (owns: business/completions/service.py, tests/unit/modules/test_completion_service.py); verify unit tests pass
- [x] 1.2 Add `app/bootstrap/services.py` (handler factory type, default echo factory, `compose_business_services`) and call it in lifespan (owns: bootstrap/{services,application}.py); verify `test_lifespan_composes_completion_service_from_handler_factory`
- [x] 1.3 `ApplicationResources.completion_service` typed field, `TaskServices` group, drop `services` registry (owns: bootstrap/{resources,state}.py); verify `test_get_task_services_*`
- [x] 1.4 Mount task routes only when `TASKS_ENABLED`; views read `get_app_resources(request.app)`; delete `completions/dependencies.py` (owns: app/api/**); verify `test_task_routes_mount_only_when_tasks_enabled`, `test_task_routes_are_not_mounted_when_tasks_disabled`
- [x] 1.5 Tests run lifespan via `api_client_for` (owns: tests/{conftest,factories}.py + affected tests); verify full pytest
- [x] 1.6 Update skill docs, README.md, TEMPLATE_GUIDE.md; verify `rg "CompletionPipeline|get_service_resource|completion_handler="` only hits historical docs

## 2. Single resource owner (step 2)

- [ ] 2.1 `open_core_resources(settings)` / close on `AsyncExitStack`, shared by API lifespan and worker; delete `_worker_needs_*` (fixes outbox+non-postgres store crash); verify worker and API resolve the same handler factory
- [ ] 2.2 Outbox store built once (opened before tasks, reused by dispatcher); verify a single instance on resources
- [ ] 2.3 Health checks registered at open time

## 3. Addons and factories (step 3, parallel per addon)

- [ ] 3.1 Move addon classes into `app/bootstrap/addons/`; factories keep `build_*` with non-optional deps; drop `app` param; declare `requires`
- [ ] 3.2 Cross-setting "X requires Y" rules in one `Settings` model validator; remove repeated checks
- [ ] 3.3 `MongoQuotaStore.ensure_indexes()` called at open (from quota-db-correctness)
