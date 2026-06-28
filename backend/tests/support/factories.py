from __future__ import annotations

import os
from typing import Any

from clay.settings.ingestion import IngestionSettings


def make_ingestion_settings(
    database_url: str | None = None,
    **kwargs: Any,
) -> IngestionSettings:
    return IngestionSettings(
        database_url=database_url or os.environ["CLAY_DATABASE_URL"],
        **kwargs,
    )
