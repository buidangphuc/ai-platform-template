.PHONY: dev test eval-smoke docker-build docker-run hygiene

dev:
	uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

eval-smoke:
	uv run pytest tests/integration/test_feedback.py -v

docker-build:
	docker build -t ai-platform-template:local .

docker-run:
	docker compose -f docker-compose.local.yaml up

hygiene:
	./scripts/check_template_hygiene.sh
