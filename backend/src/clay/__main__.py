"""Entrypoint for Clay — single-worker uvicorn.

Usage: ``python -m clay``

Reads ``CLAY_SERVER_HOST`` (default ``0.0.0.0``) and
``CLAY_SERVER_PORT`` (default ``8000``) from the environment.
Single-worker is required (ADR-007 — in-process APScheduler).
"""

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CLAY_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("CLAY_SERVER_PORT", "8000"))
    uvicorn.run(
        "clay.api.main:app",
        host=host,
        port=port,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    main()
