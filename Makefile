.DEFAULT_GOAL := help

# Image coordinates. REGISTRY is empty by default so local builds stay local.
IMAGE ?= physiotrack-api
REGISTRY ?=
IMAGE_REF := $(if $(REGISTRY),$(REGISTRY)/$(IMAGE),$(IMAGE))

# VERSION defaults to the project version; CI or the command line may override it.
VERSION ?= $(shell python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])" 2>/dev/null || sed -n -E 's/^[[:space:]]*version[[:space:]]*=[[:space:]]*["'\'']([^"'\'']+)["'\''].*/\1/p' pyproject.toml)
MAJOR := $(word 1,$(subst ., ,$(VERSION)))
MINOR := $(word 2,$(subst ., ,$(VERSION)))
PATCH := $(word 3,$(subst ., ,$(VERSION)))

# Calculate BRANCH from git if not provided
BRANCH ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# CHANNEL calculation:
# - main => empty
# - develop => alpha
# - release/* => rc
# - other => lower-kebab-case
CHANNEL ?= $(shell \
	if [ "$(BRANCH)" = "main" ]; then \
		echo ""; \
	elif [ "$(BRANCH)" = "develop" ]; then \
		echo "alpha"; \
	elif echo "$(BRANCH)" | grep -q '^release/'; then \
		echo "rc"; \
	else \
		echo "$(BRANCH)" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$$//g'; \
	fi \
)

.PHONY: install sync run test lint format clean help version check-version docker-tags docker-build docker-push docker-run

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

version: check-version ## Print the resolved version
	@echo $(VERSION)

check-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "VERSION could not be resolved from pyproject.toml. Pass VERSION=x.y.z." >&2; \
		exit 1; \
	fi

docker-tags: check-version ## Print every image tag for the current VERSION/CHANNEL
	@for v in $(MAJOR).$(MINOR).$(PATCH) $(MAJOR).$(MINOR) $(MAJOR); do \
		if [ -n "$(CHANNEL)" ]; then \
			echo "$(IMAGE_REF):$$v-$(CHANNEL)"; \
		else \
			echo "$(IMAGE_REF):$$v"; \
		fi; \
	done

docker-build: ## Build the image and apply every tag for the current channel
	docker build -t $(IMAGE_REF):build .
	@for tag in $$($(MAKE) --no-print-directory docker-tags); do \
		echo "tagging $$tag"; \
		docker tag $(IMAGE_REF):build $$tag; \
	done

docker-push: ## Push every tag for the current channel
	@for tag in $$($(MAKE) --no-print-directory docker-tags); do \
		echo "pushing $$tag"; \
		docker push $$tag; \
	done

docker-run: ## Run the freshly built image on port 8000
	docker run --rm -p 8000:8000 $(IMAGE_REF):build

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'
