"""Guard: no configuration path leads to PRODUCTION trading.

All tests are hermetic — no network, no real keys.
When any test in this file fails, real-money trading is reachable via config.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

from clay.execution.config import ExecutionConfig, environment_from_mode

MODES = {"dry_run", "live", "production", "real", "paper", "bogus", ""}


class TestEnvironmentFromModeReturnsNone:
    def test_no_mode_returns_production(self) -> None:
        for mode in MODES:
            assert environment_from_mode(mode) is None, (
                f"environment_from_mode({mode!r}) must return None — "
                f"any non-None return enables real-money trading via config"
            )


class TestNoProductionBranch:
    def test_returns_only_testnet_demo_or_none(self) -> None:
        """Функция может возвращать только TESTNET, DEMO или None.

        Белый список: каждый Return в теле функции обязан быть None или
        членом ``Environment`` из {TESTNET, DEMO}. Комментарии и докстринги
        в AST не попадают. Это ловит и ``Environment.PRODUCTION``, и любой
        будущий боевой член enum, названный иначе.
        """
        source = inspect.getsource(environment_from_mode)
        tree = ast.parse(source)
        func = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        allowed = {"TESTNET", "DEMO"}
        violations: list[str] = []
        for node in ast.walk(func):
            if not isinstance(node, ast.Return):
                continue
            if node.value is None or (
                isinstance(node.value, ast.Constant) and node.value.value is None
            ):
                continue
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "Environment"
                and node.value.attr in allowed
            ):
                continue
            violations.append(
                f"return {ast.unparse(node.value)} — разрешены только "
                "Environment.TESTNET, Environment.DEMO, None"
            )
        assert not violations, (
            "environment_from_mode нарушает белый список возвратов:\n"
            + "\n".join(violations)
        )


class TestBuildExecutionClientReturnsNone:
    def test_returns_none_when_env_is_none(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(mode="dry_run", venue="binance")
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when environment_from_mode returns None — "
            "otherwise dry_run builds a live adapter"
        )

    def test_returns_none_when_api_key_empty(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="binance", api_key="", api_secret="s"
        )
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when api_key is empty — "
            "otherwise missing credentials can reach a live adapter"
        )

    def test_returns_none_when_api_secret_empty(self) -> None:
        from clay.bootstrap import _build_execution_client

        cfg = ExecutionConfig(
            mode="testnet", venue="binance", api_key="k", api_secret=""
        )
        result = _build_execution_client(cfg)
        assert result is None, (
            "must return None when api_secret is empty — "
            "otherwise missing credentials can reach a live adapter"
        )


class TestCommentLock:
    def test_comment_lock_references_existing_test(self) -> None:
        """Комментарий-замок обязан ссылаться на реально существующий тест.

        Из комментария вытаскивается ``backend/tests/policy/<file>.py::<test>``
        и проверяется, что функция с таким именем реально определена в этом
        файле. Расхождение между замком и тестом — нарушение.
        """
        source = inspect.getsource(environment_from_mode)
        match = re.search(r"backend/tests/policy/([\w/]+\.py)::([a-z0-9_]+)", source)
        assert match, (
            "environment_from_mode должен содержать комментарий-замок вида "
            "backend/tests/policy/test_no_production_path.py::<имя_теста>"
        )
        test_file = pathlib.Path(__file__).resolve().parent / match.group(1)
        test_name = match.group(2)
        content = test_file.read_text(encoding="utf-8")
        assert re.search(rf"def {test_name}\(", content), (
            f"комментарий-замок ссылается на {match.group(1)}::{test_name}, "
            "но такого теста в этом файле нет"
        )
