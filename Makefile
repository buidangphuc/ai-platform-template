.PHONY: help dev worker grpc proto test eval lint format typecheck check ci hooks-install \
        migrate migration-new migrate-down \
        smoke-langfuse smoke-langfuse-prompt \
        docker-build docker-run docker-run-langfuse

UV_CACHE_DIR ?= .uv-cache
UV := PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=$(UV_CACHE_DIR) uv
# Dev/test run with every optional extra installed ([ai], [aws], [mongo], ...).
# Production installs pick extras explicitly: `uv sync --extra ai` etc.
UV_RUN := $(UV) run --all-extras

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Run dev server with autoreload
	$(UV_RUN) uvicorn main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run async task worker
	$(UV_RUN) python -m scripts.run_worker

grpc: ## Run the gRPC server (platform-core contract: Search + Chat)
	$(UV_RUN) python -m scripts.run_grpc

proto: ## Regenerate gRPC stubs from the vendored proto (proto/ -> app/transport/grpc/_pb)
	$(UV_RUN) python -m scripts.gen_proto

test: ## Run pytest
	$(UV_RUN) pytest -v

eval: ## Run the eval gate (deterministic cases; judge cases need JUDGE_CHAT_MODEL)
	$(UV_RUN) python -m scripts.run_eval --min-score 0.8

test-fast: ## Run pytest in parallel via pytest-xdist
	$(UV_RUN) pytest -n auto

lint: ## Ruff lint
	$(UV_RUN) ruff check .

format: ## Ruff format
	$(UV_RUN) ruff format .

check: ## Ruff lint + format check (no auto-fix)
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

check-env: ## Verify .env.example matches Settings fields
	$(UV_RUN) python -m scripts.check_env_example

typecheck: ## Pyright type check
	$(UV_RUN) pyright

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
	$(UV_RUN) python -m scripts.smoke.langfuse_callback

smoke-langfuse-prompt: ## Run Langfuse prompt smoke
	$(UV_RUN) python -m scripts.smoke.langfuse_prompt

docker-build: ## Build docker image
	docker build -t ai-platform-template:local .

docker-run: ## Run local docker compose stack
	docker compose -f docker-compose.local.yaml up

docker-run-langfuse: ## Run local stack with Langfuse (loads .env.langfuse if present)
	docker compose --env-file .env $(if $(wildcard .env.langfuse),--env-file .env.langfuse) \
	  -f docker-compose.local.yaml -f docker-compose.langfuse.yaml up
