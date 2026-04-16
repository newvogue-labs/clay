# Clay

Your own trading workspace. Signals, review, and control.

## Current Status

This repository is the implementation workspace for `Clay`.

At the moment:

- the architecture and planning phase are complete;
- implementation starts here;
- the first delivery target is `Wave 1`:
  - `E1` runtime foundation
  - `E2` data ingestion and local historical store
  - `E4` control center and runtime operations

## Repository Layout

- `backend/` — future backend application and runtime services
- `frontend/` — future web UI application
- `docs/planning/` — imported planning source documents needed during implementation
- `scripts/` — helper scripts for local development and repo automation

## Planning Source

The most important planning references live in `docs/planning/`:

- `blueprint-v1.md`
- `tech-stack-v1.md`
- `execution-backlog-v1.md`
- `master-planning-review-v1.md`

Implementation should follow those documents rather than reinvent system boundaries during coding.
