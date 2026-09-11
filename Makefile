.DEFAULT_GOAL := help

.PHONY: install sync run test lint format clean help

install: ## Install project dependencies (alias: sync)
	uv sync

sync: install ## Alias for install

run: ## Run the API with auto-reload
	uv run uvicorn main:app --reload --app-dir src

test: ## Run the test suite
	uv run pytest

lint: ## Check code style with ruff
	uv run ruff check .

format: ## Format code with ruff
	uv run ruff format .

clean: ## Remove build/test artifacts
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache *.egg-info dist build

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-10s\033[0m %s\n", $$1, $$2}'
