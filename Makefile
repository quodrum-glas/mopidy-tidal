.PHONY: lint test integration-test

lint:
	ruff check mopidy_tidal/ tests/
	ruff format --check mopidy_tidal/ tests/

test:
	pytest --cov=mopidy_tidal --cov-report=xml --cov-report=term-missing tests/

integration-test:
	python test_installation.py
