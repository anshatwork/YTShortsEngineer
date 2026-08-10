# Makefile — developer task runner for YTShortsEngine (backend).
#
# Recipes use POSIX sh (Git Bash on Windows provides `make` + sh; on Linux/macOS it's native).
# On Windows without `make`, run the underlying commands directly — each recipe is a one-liner.
# Dev tools: `ruff` + `pytest` are expected; `mypy` is optional (typecheck degrades gracefully).
#
# Quick start:  make help

PY ?= python
PYTEST ?= $(PY) -m pytest
RUFF ?= $(PY) -m ruff
TESTS_DIR ?= tests

.DEFAULT_GOAL := help

.PHONY: help install lint format format-check typecheck test test-all test-file \
        evals docs repo-map benchmark clean check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install backend + dev dependencies
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install ruff pytest mypy || true

lint: ## Lint with ruff
	$(RUFF) check .

format: ## Auto-format with ruff
	$(RUFF) format .
	$(RUFF) check --fix .

format-check: ## Verify formatting without writing (CI)
	$(RUFF) format --check .

typecheck: ## Static type check (mypy, optional)
	@$(PY) -c "import mypy" 2>/dev/null && $(PY) -m mypy agents core tools \
	 || echo "mypy not installed — skipping (pip install mypy). See docs/claude/coding-guidelines.md"

test: ## Run the maintained suite per-file (avoids shared-singleton redness; see docs/claude/testing.md)
	@set -e; for f in $(TESTS_DIR)/test_*.py; do echo "== $$f =="; $(PYTEST) "$$f" -q || exit 1; done

test-all: ## Run the whole suite at once (KNOWN red — shared task-queue singleton)
	$(PYTEST) $(TESTS_DIR) -q

test-file: ## Run one file:  make test-file F=tests/test_api.py
	$(PYTEST) $(F) -v

evals: ## Run the LLM evaluation suite (see docs/future/llm-judge.md)
	@$(PY) -c "import evals" 2>/dev/null && $(PY) -m evals.cli \
	 || echo "eval harness not implemented yet — see docs/future/llm-judge.md and .claude/skills/llm-evaluation"

docs: repo-map ## Regenerate auto-generated docs (repo map, dependency + graph maps)

repo-map: ## Regenerate docs/claude/repo-map.md (tree, graphs, routes, deps)
	$(PY) scripts/gen_repo_map.py

benchmark: ## Benchmark the clipping pipeline on the sample fixture (real ffmpeg)
	@test -f assets/ailover.mp4 && $(PY) run_clipping_workflow.py assets/ailover.mp4 --no-intro \
	 || echo "benchmark needs assets/ailover.mp4 (the test fixture). Provide a video path instead."

check: lint typecheck test ## Lint + typecheck + test (pre-push gate)

clean: ## Remove caches and generated artifacts (keeps source)
	@find . -type d -name '__pycache__' -not -path './venv/*' -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .ruff_cache 2>/dev/null || true
	@echo "cleaned pycache + tool caches (did NOT touch output/, cache/, logs/)"
