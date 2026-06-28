import io
import logging
from typing import Any

import pytest

from clay.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector
from clay.ingestion.context.contracts import ContextConnector
from clay.ingestion.context.manager import ContextConnectorManager


class _FailingConnector(ContextConnector):
    connector_id = "fail-connector"
    connector_type = "news"
    source_name = "fail_source"
    enabled = True

    async def fetch(self) -> list[dict[str, Any]]:
        msg = "simulated connector failure"
        raise RuntimeError(msg)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    async def health_check(self) -> dict[str, str]:
        return {"status": "healthy"}


def test_demo_news_connector_exposes_required_contract_fields() -> None:
    connector = DemoNewsConnector()

    assert connector.connector_id == "demo-news"
    assert connector.connector_type == "news"
    assert connector.source_name == "demo_news_feed"
    assert connector.enabled is True


def test_demo_sentiment_connector_exposes_required_contract_fields() -> None:
    connector = DemoSentimentConnector()

    assert connector.connector_id == "demo-sentiment"
    assert connector.connector_type == "sentiment"
    assert connector.source_name == "demo_sentiment_feed"


@pytest.mark.anyio
async def test_context_manager_skips_disabled_connectors() -> None:
    connector = DemoNewsConnector()
    connector.enabled = False
    manager = ContextConnectorManager([connector])

    results = await manager.run_once()

    assert len(results) == 1
    assert results[0].status == "disabled"
    assert results[0].payloads == []


@pytest.mark.anyio
async def test_context_manager_processes_enabled_connectors() -> None:
    manager = ContextConnectorManager([DemoNewsConnector(), DemoSentimentConnector()])

    results = await manager.run_once()

    assert len(results) == 2
    assert sum(len(result.payloads) for result in results) == 2
    assert all(result.status == "healthy" for result in results)


@pytest.mark.anyio
async def test_context_manager_logs_exception_on_connector_failure() -> None:
    """MP4 site 3: logger.exception fires when a connector's fetch() raises."""
    manager = ContextConnectorManager([_FailingConnector()])
    logger = logging.getLogger("clay.ingestion.context")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.ERROR)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        results = await manager.run_once()
        output = stream.getvalue()
        assert "simulated connector failure" in output, (
            f"missing exception log, got: {output}"
        )
        assert len(results) == 1
        assert results[0].status == "error"
        assert "simulated connector failure" in results[0].details.get("error", "")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
