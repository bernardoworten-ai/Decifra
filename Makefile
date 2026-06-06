# DECIFRA — atalhos de desenvolvimento
DB_URL ?= postgresql://decifra:decifra@localhost:5432/decifra

.PHONY: smoke db-up migrate seed test test-int

# Smoke: sobe a BD, migra, semeia e corre o teste de integração e2e.
smoke: db-up migrate seed test-int

db-up:
	docker compose up -d db
	@echo "→ a aguardar o Postgres…"
	@until docker compose exec -T db pg_isready -U decifra -d decifra >/dev/null 2>&1; do sleep 1; done
	@echo "✓ Postgres pronto"

migrate:
	cd web && DATABASE_URL="$(DB_URL)" npm run db:migrate

seed:
	cd web && DATABASE_URL="$(DB_URL)" npm run db:seed

# Testes unitários (offline)
test:
	cd workers && [ -d .venv ] || (python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt)
	cd workers && .venv/bin/python -m pytest -q

# Teste de integração e2e (precisa da BD a correr)
test-int:
	cd workers && [ -d .venv ] || (python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt)
	cd workers && DATABASE_URL="$(DB_URL)" .venv/bin/python -m pytest -m integration -q
