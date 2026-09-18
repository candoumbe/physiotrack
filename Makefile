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

.PHONY: install sync run test lint format clean help version check-version docker-tags docker-build docker-push docker-run feature chore coldfix release hotfix

BASE_BRANCH ?= develop
HOTFIX_BASE_BRANCH ?= main

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

define WORKFLOW
	@workflow="$(1)"; base="$(2)"; current="$$(git symbolic-ref --short -q HEAD)"; \
	project_version() { sed -n '/^\[project\]/,/^\[/ { /^[[:space:]]*version[[:space:]]*=/ { p; q; }; }' pyproject.toml; }; \
	if [ -z "$$current" ]; then \
		echo "Cannot run $$workflow from a detached HEAD." >&2; exit 1; \
	fi; \
	case "$$current" in \
		"$$workflow"/*) \
			if [ -n "$(NAME)" ] && [ "$$current" != "$$workflow/$(NAME)" ]; then \
				echo "NAME does not match the current $$workflow branch ($$current)." >&2; exit 1; \
			fi; \
			if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
				echo "Cannot finish $$current with uncommitted changes; commit or stash them first." >&2; exit 1; \
			fi; \
			git show-ref --verify --quiet "refs/heads/$$base" || { echo "Base branch not found: $$base" >&2; exit 1; }; \
			if [ "$(1)" = hotfix ]; then \
				version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
				printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml: $$version" >&2; exit 1; }; \
				tag="$$version"; \
				git rev-parse -q --verify "refs/tags/$$tag" >/dev/null && { echo "Tag already exists: $$tag" >&2; exit 1; }; \
			fi; \
			git switch "$$base" || { echo "Could not switch to $$base; workflow branch kept." >&2; exit 1; }; \
			git merge --no-ff --no-edit "$$current" || { echo "Merge conflict; resolve it on $$base. Branch $$current was kept." >&2; exit 1; }; \
			if [ "$(1)" = hotfix ]; then git tag "$$tag" || { echo "Could not create tag $$tag; branch was kept." >&2; exit 1; }; fi; \
			git branch -d "$$current" || { echo "Merged, but could not delete $$current." >&2; exit 1; } \
			;; \
		*) \
			name="$(NAME)"; \
			case "$$name" in ""|*[!A-Za-z0-9._-]*) echo "NAME is required and may contain only letters, digits, '.', '_' or '-' (example: make $(1) NAME=add-measurements)." >&2; exit 1;; esac; \
			branch="$$workflow/$$name"; \
			git check-ref-format --branch "$$branch" >/dev/null 2>&1 || { echo "Invalid branch name: $$branch" >&2; exit 1; }; \
			git show-ref --verify --quiet "refs/heads/$$base" || { echo "Base branch not found: $$base" >&2; exit 1; }; \
			git show-ref --verify --quiet "refs/heads/$$branch" && { echo "Branch already exists: $$branch" >&2; exit 1; }; \
			dirty=0; marker="make-$$workflow-$$name-$$PPID"; \
			if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
				dirty=1; git stash push --include-untracked -m "$$marker" || { echo "Could not stash current changes; workflow not started." >&2; exit 1; }; \
			fi; \
			git switch "$$base" || { echo "Could not switch to $$base; changes remain in the stash." >&2; exit 1; }; \
			git switch -c "$$branch" || { echo "Could not create $$branch; changes remain in the stash." >&2; exit 1; }; \
			if [ "$$dirty" -eq 1 ]; then git stash pop --index || { echo "Could not restore changes; resolve the conflict manually. The stash was kept for recovery." >&2; exit 1; }; fi; \
			if [ "$(1)" = hotfix ]; then \
				version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
				printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml: $$version" >&2; exit 1; }; \
				major="$${version%%.*}"; rest="$${version#*.}"; minor="$${rest%%.*}"; patch="$${rest#*.}"; new_version="$$major.$$minor.$$((patch + 1))"; \
				sed -i -E "/^\\[project\\]/,/^\\[/ s/^([[:space:]]*version[[:space:]]*=[[:space:]]*[\"']$$major\\.$$minor\\.)$$patch([\"'].*)/\\1$$((patch + 1))\\2/" pyproject.toml; \
				updated="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
				[ "$$updated" = "$$new_version" ] || { echo "Could not bump project version to $$new_version." >&2; exit 1; }; \
				echo "Hotfix version: $$new_version"; \
			fi; \
			echo "Started $$branch from $$base" \
			;; \
	esac
endef

define HOTFIX_WORKFLOW
	@workflow="hotfix"; base="$(HOTFIX_BASE_BRANCH)"; current="$$(git symbolic-ref --short -q HEAD)"; \
	project_version() { sed -n '/^\[project\]/,/^\[/ { /^[[:space:]]*version[[:space:]]*=/ { p; q; }; }' pyproject.toml; }; \
	if [ -z "$$current" ]; then echo "Cannot run $$workflow from a detached HEAD." >&2; exit 1; fi; \
	case "$$current" in \
		"$$workflow"/*) \
			if [ -n "$(NAME)" ] && [ "$$current" != "$$workflow/$(NAME)" ]; then echo "NAME does not match the current $$workflow branch ($$current)." >&2; exit 1; fi; \
			if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then echo "Cannot finish $$current with uncommitted changes; commit or stash them first." >&2; exit 1; fi; \
			git show-ref --verify --quiet "refs/heads/$$base" || { echo "Base branch not found: $$base" >&2; exit 1; }; \
			version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
			printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml: $$version" >&2; exit 1; }; \
			changelog="CHANGELOG.md"; release_heading="## [$$version] - $$(date +%F)"; \
			[ -f "$$changelog" ] || { echo "Changelog not found: $$changelog" >&2; exit 1; }; \
			unreleased_count="$$(grep -c '^## \[Unreleased\]$$' "$$changelog" || true)"; \
			[ "$$unreleased_count" -eq 1 ] || { echo "Changelog must contain exactly one ## [Unreleased] section." >&2; exit 1; }; \
			release_count="$$(grep -Fc "$$release_heading" "$$changelog" || true)"; \
			[ "$$release_count" -le 1 ] || { echo "Changelog contains the release heading more than once: $$release_heading" >&2; exit 1; }; \
			unreleased_content() { awk ' \
				$$0 == "## [Unreleased]" { in_section=1; next } \
				in_section && (/^## / || /^\[Unreleased\]:/) { in_section=0 } \
				in_section && $$0 !~ /^[[:space:]]*$$/ { found=1 } \
				END { exit !found }' "$$changelog"; \
			}; \
			if [ "$$release_count" -eq 1 ]; then \
				if unreleased_content; then echo "[Unreleased] is not empty although $$release_heading already exists." >&2; exit 1; fi; \
			else \
				tmp="$$(mktemp "$${TMPDIR:-/tmp}/physiotrack-changelog.XXXXXX")" || { echo "Could not create temporary changelog." >&2; exit 1; }; \
				if ! awk -v title="$$release_heading" ' \
					$$0 == "## [Unreleased]" { print; print; print title; in_section=1; next } \
					in_section && (/^## / || /^\[Unreleased\]:/) { in_section=0 } \
					{ print }' "$$changelog" > "$$tmp"; then rm -f "$$tmp"; echo "Could not prepare $$changelog." >&2; exit 1; fi; \
				mv "$$tmp" "$$changelog" || { rm -f "$$tmp"; echo "Could not update $$changelog." >&2; exit 1; }; \
				if ! git diff --quiet -- "$$changelog"; then echo "Changelog prepared for $$release_heading. Commit $$changelog, then rerun make hotfix." >&2; exit 1; fi; \
			fi; \
			git switch "$$base" || { echo "Could not switch to $$base; hotfix branch kept." >&2; exit 1; }; \
			if ! git merge --no-ff --no-edit "$$current"; then \
				git merge --abort 2>/dev/null || true; git switch "$$current" 2>/dev/null || true; echo "Merge conflict merging $$current into $$base; hotfix branch was kept." >&2; exit 1; \
			fi; \
			version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
			printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml after merge: $$version" >&2; exit 1; }; \
			tag="v$$version"; git rev-parse -q --verify "refs/tags/$$tag" >/dev/null && { echo "Tag already exists: $$tag" >&2; exit 1; }; \
			git tag "$$tag" || { echo "Could not create tag $$tag; branch was kept." >&2; exit 1; }; \
			git branch -d "$$current" || { echo "Merged and tagged $$tag, but could not delete $$current." >&2; exit 1; }; \
			echo "Finalized $$current: changelog released, merged into $$base, tagged $$tag, branch deleted." \
			;; \
		*) \
			name="$(NAME)"; case "$$name" in ""|*[!A-Za-z0-9._-]*) echo "NAME is required and may contain only letters, digits, '.', '_' or '-' (example: make hotfix NAME=fix-measurements)." >&2; exit 1;; esac; \
			branch="$$workflow/$$name"; git check-ref-format --branch "$$branch" >/dev/null 2>&1 || { echo "Invalid branch name: $$branch" >&2; exit 1; }; \
			git show-ref --verify --quiet "refs/heads/$$base" || { echo "Base branch not found: $$base" >&2; exit 1; }; git show-ref --verify --quiet "refs/heads/$$branch" && { echo "Branch already exists: $$branch" >&2; exit 1; }; \
			dirty=0; marker="make-$$workflow-$$name-$$PPID"; if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then dirty=1; git stash push --include-untracked -m "$$marker" || { echo "Could not stash current changes; workflow not started." >&2; exit 1; }; fi; \
			git switch "$$base" || { echo "Could not switch to $$base; changes remain in the stash." >&2; exit 1; }; git switch -c "$$branch" || { echo "Could not create $$branch; changes remain in the stash." >&2; exit 1; }; \
			if [ "$$dirty" -eq 1 ]; then git stash pop --index || { echo "Could not restore changes; resolve the conflict manually. The stash was kept for recovery." >&2; exit 1; }; fi; \
			version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml: $$version" >&2; exit 1; }; \
			major="$${version%%.*}"; rest="$${version#*.}"; minor="$${rest%%.*}"; patch="$${rest#*.}"; new_version="$$major.$$minor.$$((patch + 1))"; \
			sed -i -E "/^\[project\]/,/^\[/ s/^([[:space:]]*version[[:space:]]*=[[:space:]]*[\"']$$major\.$$minor\.)$$patch([\"'].*)/\\1$$((patch + 1))\\2/" pyproject.toml; updated="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
			[ "$$updated" = "$$new_version" ] || { echo "Could not bump project version to $$new_version." >&2; exit 1; }; echo "Hotfix version: $$new_version"; echo "Started $$branch from $$base" \
			;; \
	esac
endef

define RELEASE_WORKFLOW
	@workflow="release"; current="$$(git symbolic-ref --short -q HEAD)"; \
	project_version() { sed -n '/^\[project\]/,/^\[/ { /^[[:space:]]*version[[:space:]]*=/ { p; q; }; }' pyproject.toml; }; \
	if [ -z "$$current" ]; then \
		echo "Cannot run $$workflow from a detached HEAD." >&2; exit 1; \
	fi; \
	case "$$current" in \
		"$$workflow"/*) \
			if [ -n "$(NAME)" ] && [ "$$current" != "$$workflow/$(NAME)" ]; then \
				echo "NAME does not match the current $$workflow branch ($$current)." >&2; exit 1; \
			fi; \
			if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
				echo "Cannot finish $$current with uncommitted changes; commit or stash them first." >&2; exit 1; \
			fi; \
			git show-ref --verify --quiet refs/heads/main || { echo "Base branch not found: main" >&2; exit 1; }; \
			git show-ref --verify --quiet refs/heads/develop || { echo "Base branch not found: develop" >&2; exit 1; }; \
			version="$$(project_version | sed -E "s/^[^=]*=[[:space:]]*[\"']([^\"']+)[\"'][[:space:]]*$$/\\1/")"; \
			printf '%s\n' "$$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "Invalid project SemVer in pyproject.toml: $$version" >&2; exit 1; }; \
			changelog="CHANGELOG.md"; release_heading="## [$$version] - $$(date +%F)"; \
			[ -f "$$changelog" ] || { echo "Changelog not found: $$changelog" >&2; exit 1; }; \
			unreleased_count="$$(grep -c '^## \[Unreleased\]$$' "$$changelog" || true)"; \
			[ "$$unreleased_count" -eq 1 ] || { echo "Changelog must contain exactly one ## [Unreleased] section." >&2; exit 1; }; \
			release_count="$$(grep -Fc "$$release_heading" "$$changelog" || true)"; \
			[ "$$release_count" -le 1 ] || { echo "Changelog contains the release heading more than once: $$release_heading" >&2; exit 1; }; \
			unreleased_content() { awk ' \
				$$0 == "## [Unreleased]" { in_section=1; next } \
				in_section && (/^## / || /^\[Unreleased\]:/) { in_section=0 } \
				in_section && $$0 !~ /^[[:space:]]*$$/ { found=1 } \
				END { exit !found }' "$$changelog"; \
			}; \
			if [ "$$release_count" -eq 1 ]; then \
				if unreleased_content; then echo "[Unreleased] is not empty although $$release_heading already exists." >&2; exit 1; fi; \
			else \
				tmp="$$(mktemp "$${TMPDIR:-/tmp}/physiotrack-changelog.XXXXXX")" || { echo "Could not create temporary changelog." >&2; exit 1; }; \
				if ! awk -v title="$$release_heading" ' \
					$$0 == "## [Unreleased]" { print; print title; in_section=1; next } \
					in_section && (/^## / || /^\[Unreleased\]:/) { in_section=0 } \
					{ print }' "$$changelog" > "$$tmp"; then rm -f "$$tmp"; echo "Could not prepare $$changelog." >&2; exit 1; fi; \
				mv "$$tmp" "$$changelog" || { rm -f "$$tmp"; echo "Could not update $$changelog." >&2; exit 1; }; \
				if ! git diff --quiet -- "$$changelog"; then \
					echo "Changelog prepared for $$release_heading. Commit $$changelog, then rerun make release." >&2; exit 1; \
				fi; \
			fi; \
			git switch main || { echo "Could not switch to main; release branch kept." >&2; exit 1; }; \
			if ! git merge --no-ff --no-edit "$$current"; then \
				git merge --abort 2>/dev/null || true; git switch "$$current" 2>/dev/null || true; \
				echo "Merge conflict merging $$current into main; release branch was kept." >&2; exit 1; \
			fi; \
			git switch develop || { echo "Could not switch to develop; release branch kept." >&2; exit 1; }; \
			if ! git merge --no-ff --no-edit main; then \
				git merge --abort 2>/dev/null || true; git switch "$$current" 2>/dev/null || true; \
				echo "Merge conflict merging main into develop; release branch was kept." >&2; exit 1; \
			fi; \
			git branch -d "$$current" || { echo "Merged, but could not delete $$current." >&2; exit 1; }; \
			echo "Finalized $$current: changelog released, merged into main and develop, branch deleted." \
			;; \
		*) \
			name="$(NAME)"; \
			case "$$name" in ""|*[!A-Za-z0-9._-]*) echo "NAME is required and may contain only letters, digits, '.', '_' or '-' (example: make release NAME=2026-09-18)." >&2; exit 1;; esac; \
			branch="release/$$name"; \
			git check-ref-format --branch "$$branch" >/dev/null 2>&1 || { echo "Invalid branch name: $$branch" >&2; exit 1; }; \
			git show-ref --verify --quiet "refs/heads/$(BASE_BRANCH)" || { echo "Base branch not found: $(BASE_BRANCH)" >&2; exit 1; }; \
			git show-ref --verify --quiet "refs/heads/$$branch" && { echo "Branch already exists: $$branch" >&2; exit 1; }; \
			dirty=0; marker="make-release-$$name-$$PPID"; \
			if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
				dirty=1; git stash push --include-untracked -m "$$marker" || { echo "Could not stash current changes; workflow not started." >&2; exit 1; }; \
			fi; \
			git switch "$(BASE_BRANCH)" || { echo "Could not switch to $(BASE_BRANCH); changes remain in the stash." >&2; exit 1; }; \
			git switch -c "$$branch" || { echo "Could not create $$branch; changes remain in the stash." >&2; exit 1; }; \
			if [ "$$dirty" -eq 1 ]; then git stash pop --index || { echo "Could not restore changes; resolve the conflict manually. The stash was kept for recovery." >&2; exit 1; }; fi; \
			echo "Started $$branch from $(BASE_BRANCH)" \
			;; \
	esac
endef

feature: ## Start or finish feature/NAME (base: develop)
	$(call WORKFLOW,feature,$(BASE_BRANCH))

chore: ## Start or finish chore/NAME (base: develop)
	$(call WORKFLOW,chore,$(BASE_BRANCH))

coldfix: ## Start or finish coldfix/NAME (base: develop)
	$(call WORKFLOW,coldfix,$(BASE_BRANCH))

release: ## Start or finish release/NAME (base: develop; finish commits CHANGELOG.md first, then rerun)
	$(call RELEASE_WORKFLOW)

hotfix: ## Start or finish hotfix/NAME (base: main; finish commits CHANGELOG.md first, then rerun)
	$(call HOTFIX_WORKFLOW)

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'
