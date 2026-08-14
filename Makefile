PYTHON ?= uv run python
setup: install
install:
	uv sync
	cd remotion && pnpm install
sync-types:
	PYTHONPATH=src $(PYTHON) -c "from content_creator.schemas.exporter import export_types; export_types('remotion/src/types.ts')"
test:
	PYTHONPATH=src $(PYTHON) -m pytest -q
render:
	$(PYTHON) -m content_creator.main --images ./input/images --audio ./input/bgm.wav
web:
	PYTHONPATH=src $(PYTHON) -m uvicorn content_creator.web:app --host 127.0.0.1 --port 8000
browser:
	$(PYTHON) -m playwright install chromium
clean:
	rm -rf .pytest_cache output/projects/* remotion/node_modules
