.PHONY: dev test eval-smoke smoke-langfuse smoke-langfuse-prompt docker-build docker-run docker-run-langfuse hygiene

UV_CACHE_DIR ?= .uv-cache

dev:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run pytest -v

eval-smoke:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m research.evaluation.run_rag_smoke

smoke-langfuse:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m scripts.smoke.langfuse_callback

smoke-langfuse-prompt:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m scripts.smoke.langfuse_prompt

docker-build:
	docker build -t ai-platform-template:local .

docker-run:
	docker compose -f docker-compose.local.yaml up

docker-run-langfuse:
	docker compose -f docker-compose.local.yaml -f docker-compose.langfuse.yaml up

hygiene:
	./scripts/check_template_hygiene.sh
