.PHONY: help dev worker test test-fast test-ci eval-ci hooks verify check-env test-infra infra-up eval lint format typecheck arch check ci new-domain hooks-install \
        migrate migration-new migrate-down \
        smoke-langfuse smoke-langfuse-prompt \
        docker-build docker-run docker-run-langfuse

UV_CACHE_DIR ?= .uv-cache
UV := PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=$(UV_CACHE_DIR) uv
# Dev/test run with every optional extra installed ([ai], [aws], [mongo], ...).
# Production installs pick extras explicitly: `uv sync --extra ai` etc.
UV_RUN := $(UV) run --all-extras
SRC := app tests scripts alembic
LOCALINFRA_DIR ?= $(HOME)/Documents/localinfra

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

dev: ## Run dev server with autoreload
	$(UV_RUN) uvicorn main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run async task worker
	$(UV_RUN) python -m scripts.run_worker

test: ## Run pytest without infra (what CI runs)
	$(UV_RUN) pytest -q -m "not infra"

infra-up: ## Start the localinfra services the tests need
	cd $(LOCALINFRA_DIR) && bin/li up redis postgres mongo minio elasticmq rabbitmq

test-infra: ## Run every test on localinfra with the 80% coverage gate
	$(UV_RUN) --env-file .env.test pytest -q --cov=app --cov-fail-under=80

eval: ## Run the eval gate (deterministic cases; judge cases need JUDGE_CHAT_MODEL)
	$(UV_RUN) python -m scripts.run_eval --min-score 0.8

test-ci: ## Tests without infra, with the CI coverage gate
	$(UV_RUN) pytest -q -m "not infra" --cov=app --cov-report=term-missing --cov-fail-under=74

eval-ci: ## Eval gate on .env.example defaults
	$(UV) run --env-file .env.example --all-extras python -m scripts.run_eval --min-score 0.8

test-fast: ## Run pytest in parallel via pytest-xdist
	$(UV_RUN) pytest -n auto -m "not infra"

lint: ## Ruff lint
	$(UV_RUN) ruff check $(SRC)

format: ## Ruff format
	$(UV_RUN) ruff format $(SRC)

check: ## Ruff lint + format check (no auto-fix)
	$(UV_RUN) ruff check $(SRC)
	$(UV_RUN) ruff format --check $(SRC)

check-env: ## Verify .env.example matches Settings fields
	$(UV_RUN) python -m scripts.check_env_example

typecheck: ## Pyright type check
	$(UV_RUN) pyright

arch: ## Enforce layer import rules
	$(UV_RUN) lint-imports

hooks: ## Run all pre-commit hooks (commit-msg stage skipped)
	SKIP=commitizen $(UV) run pre-commit run --all-files --hook-stage pre-commit

verify: check typecheck arch hooks test-ci eval-ci ## Exactly what CI runs

ci: verify test-infra ## verify plus every test on real services

new-domain: ## Scaffold a business domain: make new-domain NAME=orders
	$(UV_RUN) python -m scripts.new_domain $(NAME)

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
	docker compose --project-directory . -f ops/compose/local.yaml up

docker-run-langfuse: ## Run local stack with Langfuse (loads .env.langfuse if present)
	docker compose --project-directory . --env-file .env $(if $(wildcard .env.langfuse),--env-file .env.langfuse) \
	  -f ops/compose/local.yaml -f ops/compose/langfuse.yaml up
