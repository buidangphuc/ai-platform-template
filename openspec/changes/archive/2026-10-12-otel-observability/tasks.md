## 1. Extra and settings

Owns: `pyproject.toml`, `uv.lock`, `app/core/config/{telemetry,__init__}.py`, `.env.example`, `tests/unit/core/test_config.py`

- [x] 1.1 `otel` extra; verify `uv sync --all-extras` and app import without the extra
- [x] 1.2 Settings mixin with endpoint validator; verify `test_enabling_telemetry_requires_an_endpoint`, `test_sample_ratio_is_bounded`, `test_telemetry_is_off_by_default_and_needs_no_endpoint`

## 2. Lifecycle

Owns: `app/core/{telemetry,telemetry_otel}.py`, `app/bootstrap/{application,resources}.py`, `app/bootstrap/addons/{telemetry,base}.py`

- [x] 2.1 Addon, handle, shutdown, instrumentation call; verify `test_telemetry_off_creates_no_provider`, `test_addon_builds_the_handle_and_shuts_it_down_on_close`, `test_create_app_instruments_fastapi_only_when_enabled`

## 3. Completions edge

Owns: `app/api/v1/completions/{observability,sync,stream}.py`

- [x] 3.1 GenAI metrics and span via the sink; verify `test_sync_completion_records_genai_histograms_without_content`, `test_stream_completion_records_time_to_first_chunk`, `test_failed_completion_is_labelled_error_without_response_model`

## 4. Docs

- [x] 4.1 Rewrite `ops/observability/README.md`
