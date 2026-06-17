.PHONY: help dev test lint format typecheck check ci hooks-install \
        migrate migration-new migrate-down \
        smoke-langfuse smoke-langfuse-prompt \
        docker-build docker-run docker-run-langfuse

UV_CACHE_DIR ?= .uv-cache
UV := PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=$(UV_CACHE_DIR) uv

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Run dev server with autoreload
	$(UV) run uvicorn main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run async task worker
	$(UV) run python -m scripts.run_worker

test: ## Run pytest
	$(UV) run pytest -v

test-fast: ## Run pytest in parallel via pytest-xdist
	$(UV) run pytest -n auto

lint: ## Ruff lint
	$(UV) run ruff check .

format: ## Ruff format
	$(UV) run ruff format .

check: ## Ruff lint + format check (no auto-fix)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

check-env: ## Verify .env.example matches Settings fields
	$(UV) run python -m scripts.check_env_example

typecheck: ## Pyright type check
	$(UV) run pyright

ci: check check-env typecheck test ## Full CI suite locally

hooks-install: ## Install pre-commit hooks
	$(UV) run pre-commit install --install-hooks

migrate: ## Run alembic upgrade head
	$(UV) run alembic upgrade head

migration-new: ## Create new migration: make migration-new NAME=add_users
	$(UV) run alembic revision --autogenerate -m "$(NAME)"

migrate-down: ## Revert last alembic migration
	$(UV) run alembic downgrade -1

smoke-langfuse: ## Run Langfuse callback smoke
	$(UV) run python -m scripts.smoke.langfuse_callback

smoke-langfuse-prompt: ## Run Langfuse prompt smoke
	$(UV) run python -m scripts.smoke.langfuse_prompt

docker-build: ## Build docker image
	docker build -t ai-platform-template:local .

docker-run: ## Run local docker compose stack
	docker compose -f docker-compose.local.yaml up

docker-run-langfuse: ## Run local stack with Langfuse (loads .env.langfuse if present)
	docker compose --env-file .env $(if $(wildcard .env.langfuse),--env-file .env.langfuse) \
	  -f docker-compose.local.yaml -f docker-compose.langfuse.yaml up
