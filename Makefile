.PHONY: backend-install backend-test backend-run frontend-install frontend-test frontend-build frontend-run

backend-install:
	cd backend && uv sync

backend-test:
	cd backend && uv run pytest

backend-run:
	cd backend && uv run uvicorn clay.api.main:app --host 127.0.0.1 --port 8000 --reload

frontend-install:
	cd frontend && pnpm install

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build

frontend-run:
	cd frontend && pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort
