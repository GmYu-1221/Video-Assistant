PYTHON ?= uv run python

install:
	uv sync

web:
	PYTHONPATH=src $(PYTHON) -m uvicorn content_creator.web:app --host 127.0.0.1 --port 8000

browser:
	$(PYTHON) -m playwright install chromium

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

clean:
	rm -rf .pytest_cache .playwright
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
