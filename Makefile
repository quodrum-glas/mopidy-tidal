.PHONY: lint test integration-test

lint:
	uv run ruff check mopidy_tidal/ tests/
	uv run ruff format --check mopidy_tidal/ tests/

test:
	uv run pytest --cov=mopidy_tidal --cov-report=xml --cov-report=term-missing tests/

integration-test:
	uv run python test_installation.py
