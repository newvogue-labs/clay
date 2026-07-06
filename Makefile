.PHONY: backend-install backend-test backend-run backend-lint backend-format backend-format-check backend-typecheck backend-typecheck-src backend-sync frontend-install frontend-test frontend-build frontend-run lint format format-check typecheck check frontend-typecheck

backend-install:
	cd backend && uv sync

backend-test:
	cd backend && uv run pytest

backend-lint:
	cd backend && uv run ruff check .

backend-format:
	cd backend && uv run ruff format .

backend-format-check:
	cd backend && uv run ruff format --check .

backend-typecheck:
	cd backend && uv run pyright

backend-typecheck-src:
	cd backend && uv run pyright src

lint: backend-lint

format: backend-format

format-check: backend-format-check

frontend-typecheck:
	cd frontend && pnpm run typecheck

typecheck: backend-typecheck frontend-typecheck

# Локальное зеркало CI-гейта (pyright informational — не входит).
check: lint format-check backend-test frontend-typecheck frontend-test

backend-sync:
	cd backend && uv run python -m clay.knowledge.sync

backend-eval-m278:
	cd backend && uv run python scripts/eval/m278_scan.py /tmp/summary_inject.txt /tmp/summary_off.txt

backend-eval-ablation:
	cd backend && uv run python scripts/eval/knowledge_ablation_llm.py

backend-run:
	cd backend && uv run uvicorn clay.api.main:app --host 127.0.0.1 --port 8000 --reload --env-file .env

frontend-install:
	cd frontend && pnpm install

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build

frontend-run:
	cd frontend && pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort
