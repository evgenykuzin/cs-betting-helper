.PHONY: up down build logs ps shell db-shell poll

# ── Docker ──
up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

ps:
	docker compose ps

# ── Shortcuts ──
shell:
	docker compose exec web bash

db-shell:
	docker compose exec postgres psql -U cs_user -d cs_betting

redis-cli:
	docker compose exec redis redis-cli

# ── Celery ──
worker-logs:
	docker compose logs -f worker

beat-logs:
	docker compose logs -f beat

# ── Manual trigger ──
poll:
	curl -X POST http://localhost:8000/api/poll

# ── Dev ──
dev:
	uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check app/

# ── DB ──
db-init:
	docker compose exec postgres psql -U cs_user -d cs_betting -f /docker-entrypoint-initdb.d/01-schema.sql
