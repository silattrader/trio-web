.PHONY: install test run lint

install:
	pip install -e packages/algorithms
	pip install -e packages/data_providers
	pip install -e packages/backtester
	pip install -e "apps/api[dev]"

test:
	cd apps/api && pytest -q

run:
	cd apps/api && uvicorn app.main:app --reload --port 8001

lint:
	cd apps/api && ruff check . && ruff check ../../packages/algorithms
