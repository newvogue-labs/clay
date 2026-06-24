"""Tests for clay.core.logging configuration invariants."""
from __future__ import annotations

import io
import logging
import re

import pytest

from clay.core.logging import configure_clay_logging


def _reset_clay_logging() -> None:
    logger = logging.getLogger("clay")
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    logger.propagate = True
    logger.setLevel(logging.NOTSET)
    import clay.core.logging as cl
    cl._CONFIGURED = False


class TestLoggingConfig:
    def test_propagate_false(self) -> None:
        _reset_clay_logging()
        configure_clay_logging()
        assert logging.getLogger("clay").propagate is False

    def test_anti_dup_guard(self) -> None:
        _reset_clay_logging()
        configure_clay_logging()
        configure_clay_logging()
        assert len(logging.getLogger("clay").handlers) == 1

    def test_level_default(self) -> None:
        _reset_clay_logging()
        configure_clay_logging()
        assert logging.getLogger("clay").level == logging.INFO

    def test_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_clay_logging()
        monkeypatch.setenv("CLAY_LOG_LEVEL", "DEBUG")
        configure_clay_logging()
        assert logging.getLogger("clay").level == logging.DEBUG

    def test_level_from_env_invalid_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_clay_logging()
        monkeypatch.setenv("CLAY_LOG_LEVEL", "BOGUS")
        configure_clay_logging()
        assert logging.getLogger("clay").level == logging.INFO

    def test_emitted_record_has_expected_format(self) -> None:
        _reset_clay_logging()
        configure_clay_logging()
        logger = logging.getLogger("clay.test")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        try:
            logger.info("hello clay")
            output = stream.getvalue()
            assert re.search(r"\d{4}-\d{2}-\d{2}.*INFO.*clay\.test: hello clay", output), f"got: {output}"
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
