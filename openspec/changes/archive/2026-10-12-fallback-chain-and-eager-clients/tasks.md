## 1. LLM fallback chain

- [x] 1.1 Router chain, per-target breakers, `try_acquire`, `select_target` raising when all open. Verify: `tests/unit/modules/test_llm_router.py` (`test_model_router_chain_*`, `test_each_chain_target_has_its_own_breaker`, `test_select_target_*`)
- [x] 1.2 `LLMInstance.ainvoke` walks the chain. Verify: `tests/unit/modules/test_llm_runtime.py` (`test_ainvoke_walks_the_whole_chain_on_transient_errors`, `::test_ainvoke_skips_targets_whose_breaker_is_open`, `::test_ainvoke_stops_on_a_deterministic_error_mid_chain`, `::test_ainvoke_raises_the_last_error_when_the_chain_is_exhausted`, `::test_ainvoke_raises_unavailable_when_every_breaker_is_open`)
- [x] 1.3 `ai-engineering.md` model selection. Verify: read-through

## 2. Eager clients

- [x] 2.1 S3 / SQS / RabbitMQ `open()`, lazy init removed. Verify: `test_s3.py`, `test_optional_extras.py`, `test_rabbitmq.py` (`test_open_queue_gateway_connects_and_declares_before_first_use`, `test_open_closes_the_connection_when_topology_declaration_fails`, `test_open_fails_fast_when_the_broker_is_unreachable`)
- [x] 2.2 Bootstrap opens them (`open_queue_gateway`, `open_object_gateway`). Verify: `test_application_lifespan.py`, `test_run_worker_entry.py`, `tests/unit/modules/objects/test_factory.py`
- [x] 2.3 Webhook dispatcher takes a bootstrap-owned `httpx.AsyncClient`. Verify: `test_webhooks.py` (`test_http_webhook_dispatcher_*`, `test_webhook_addon_owns_the_http_client_and_closes_it_on_the_stack`)

## 3. Health checks at open

- [x] 3.1 `HealthChecks` registry, concurrent bounded checks, `HEALTH_CHECK_TIMEOUT_SECONDS`. Verify: `tests/unit/core/test_health_service.py`, `check-env-example`
- [x] 3.2 Openers register postgres, redis, mongo; `ModelServerClient.check`. Verify: `test_application_lifespan.py::test_openers_register_readiness_checks_with_the_configured_timeout`, `test_mongo.py::test_mongo_addon_opens_and_closes_gateway`, `test_model_server_client.py::test_check_passes_when_healthy_and_raises_when_down`
