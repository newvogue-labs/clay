import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from clay.ingestion.context.contracts import ContextConnector

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConnectorRunResult:
    connector_id: str
    connector_type: str
    source_name: str
    status: str
    payloads: list[dict[str, Any]]
    started_at: datetime
    finished_at: datetime
    details: dict[str, Any]


class ContextConnectorManager:
    """Runs pluggable external context connectors in a unified loop."""

    def __init__(self, connectors: list[ContextConnector]) -> None:
        self._connectors = connectors

    async def run_once(self) -> list[ConnectorRunResult]:
        results: list[ConnectorRunResult] = []
        for connector in self._connectors:
            started_at = datetime.now(UTC)
            if not connector.enabled:
                results.append(
                    ConnectorRunResult(
                        connector_id=connector.connector_id,
                        connector_type=connector.connector_type,
                        source_name=connector.source_name,
                        status="disabled",
                        payloads=[],
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        details={"reason": "connector disabled"},
                    ),
                )
                continue

            try:
                payloads = await connector.fetch()
                normalized = [connector.normalize(payload) for payload in payloads]
                health = await connector.health_check()
                results.append(
                    ConnectorRunResult(
                        connector_id=connector.connector_id,
                        connector_type=connector.connector_type,
                        source_name=connector.source_name,
                        status=str(health.get("status", "healthy")),
                        payloads=normalized,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        details=dict(health),
                    ),
                )
            except Exception as exc:  # pragma: no cover - defensive runtime branch
                logger.exception(
                    "clay.ingestion.context: connector %s (%s) failed",
                    connector.connector_id,
                    connector.source_name,
                )
                results.append(
                    ConnectorRunResult(
                        connector_id=connector.connector_id,
                        connector_type=connector.connector_type,
                        source_name=connector.source_name,
                        status="error",
                        payloads=[],
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        details={"error": str(exc)},
                    ),
                )
        return results
