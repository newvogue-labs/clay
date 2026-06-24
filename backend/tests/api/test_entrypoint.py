"""Tests for ``clay/__main__.py`` (MP2 — prod entrypoint)."""

from __future__ import annotations

from unittest.mock import ANY, patch


def test_main_uses_single_worker() -> None:
    from clay.__main__ import main

    with patch("clay.__main__.uvicorn.run") as mock_run:
        main()

    mock_run.assert_called_once_with(
        "clay.api.main:app",
        host=ANY,
        port=ANY,
        workers=1,
        reload=False,
    )


def test_main_host_default() -> None:
    from clay.__main__ import main

    with patch("clay.__main__.uvicorn.run") as mock_run:
        main()

    assert mock_run.call_args.kwargs["host"] == "127.0.0.1"


def test_main_host_from_env() -> None:
    import os

    os.environ["CLAY_SERVER_HOST"] = "127.0.0.1"
    try:
        from clay.__main__ import main

        with patch("clay.__main__.uvicorn.run") as mock_run:
            main()

        assert mock_run.call_args.kwargs["host"] == "127.0.0.1"
    finally:
        os.environ.pop("CLAY_SERVER_HOST", None)


def test_main_port_default() -> None:
    from clay.__main__ import main

    with patch("clay.__main__.uvicorn.run") as mock_run:
        main()

    assert mock_run.call_args.kwargs["port"] == 8000


def test_main_port_from_env() -> None:
    import os

    os.environ["CLAY_SERVER_PORT"] = "9000"
    try:
        from clay.__main__ import main

        with patch("clay.__main__.uvicorn.run") as mock_run:
            main()

        assert mock_run.call_args.kwargs["port"] == 9000
    finally:
        os.environ.pop("CLAY_SERVER_PORT", None)
