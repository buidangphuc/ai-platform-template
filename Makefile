.PHONY: dev test eval-smoke docker-build docker-run hygiene

UV_CACHE_DIR ?= .uv-cache

dev:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run pytest -v

eval-smoke:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m research.evaluation.run_rag_smoke

docker-build:
	docker build -t ai-platform-template:local .

docker-run:
	docker compose -f docker-compose.local.yaml up

hygiene:
	./scripts/check_template_hygiene.sh
