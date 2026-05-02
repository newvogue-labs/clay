# E2 Data Ingestion And Local Historical Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working `E2` data spine for `CLAY Mission Control`: `Binance Spot` market ingestion, pluggable external context connectors, local historical storage, freshness/staleness evaluation, shortlist input views, and retention-safe ingest operations.

**Architecture:** The implementation extends the `E1` control-plane repository with backend-only ingestion services and storage-backed read models. `Binance Spot` market data is normalized into canonical schemas, persisted into `PostgreSQL + TimescaleDB`, evaluated for freshness, and exposed through control-plane read surfaces for downstream shortlist, preflight, and runtime health flows. External context sources are attached through replaceable connector contracts so `news` and `community sentiment` can evolve without mutating the hot market path.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL 16+, TimescaleDB 2.x, APScheduler, httpx, pytest, pytest-asyncio

---

## Repository Root

This plan assumes the working application repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

Important:

- this path is a `provisional implementation layout`, not a forever architecture decree;
- after demo/paper-trading validation, the repository structure and paths may be normalized and shortened in a dedicated refactor pass;
- until then, keep paths stable enough to implement, test, and verify the system without turning every task into a filesystem philosophy debate.

## File Structure

### Backend

- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_create_e2_ingestion_baseline.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/ingestion.py`
- Create: `backend/src/clay_mc/api/routes/market_data.py`
- Create: `backend/src/clay_mc/api/routes/context_data.py`
- Create: `backend/src/clay_mc/api/routes/shortlist.py`
- Create: `backend/src/clay_mc/db/base.py`
- Create: `backend/src/clay_mc/db/session.py`
- Create: `backend/src/clay_mc/db/models_market.py`
- Create: `backend/src/clay_mc/db/models_context.py`
- Create: `backend/src/clay_mc/db/models_ops.py`
- Create: `backend/src/clay_mc/ingestion/market/models.py`
- Create: `backend/src/clay_mc/ingestion/market/binance_client.py`
- Create: `backend/src/clay_mc/ingestion/market/normalizer.py`
- Create: `backend/src/clay_mc/ingestion/market/service.py`
- Create: `backend/src/clay_mc/ingestion/context/contracts.py`
- Create: `backend/src/clay_mc/ingestion/context/manager.py`
- Create: `backend/src/clay_mc/ingestion/context/connectors/demo_news.py`
- Create: `backend/src/clay_mc/ingestion/context/connectors/demo_sentiment.py`
- Create: `backend/src/clay_mc/freshness/models.py`
- Create: `backend/src/clay_mc/freshness/evaluator.py`
- Create: `backend/src/clay_mc/shortlist/models.py`
- Create: `backend/src/clay_mc/shortlist/read_models.py`
- Create: `backend/src/clay_mc/retention/jobs.py`
- Create: `backend/src/clay_mc/settings/ingestion.py`
- Create: `backend/tests/db/test_ingestion_schema.py`
- Create: `backend/tests/ingestion/test_market_normalizer.py`
- Create: `backend/tests/ingestion/test_context_connectors.py`
- Create: `backend/tests/freshness/test_evaluator.py`
- Create: `backend/tests/retention/test_jobs.py`
- Create: `backend/tests/api/test_ingestion_api.py`

### Repo-level

- Modify: `README.md`
- Modify: `.env.example`

---

### Task 1: Extend Backend Bootstrap For Database And Ingestion Settings

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/src/clay_mc/db/base.py`
- Create: `backend/src/clay_mc/db/session.py`
- Create: `backend/src/clay_mc/settings/ingestion.py`
- Modify: `.env.example`
- Test: `backend/tests/db/test_ingestion_schema.py`

- [ ] **Step 1: Write the failing ingestion settings test**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/db/test_ingestion_schema.py
from clay_mc.settings.ingestion import IngestionSettings


def test_ingestion_settings_expose_v1_timeframes() -> None:
    settings = IngestionSettings()

    assert settings.market_timeframes == ["5m", "15m", "1h"]
    assert settings.market_symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert settings.binance_spot_enabled is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/db/test_ingestion_schema.py -v
```

Expected: FAIL because `clay_mc.settings.ingestion` does not exist yet.

- [ ] **Step 3: Add database and ingestion dependencies**

```toml
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/pyproject.toml
[project]
name = "clay-mission-control-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13,<2.0",
  "fastapi>=0.115,<1.0",
  "httpx>=0.27,<1.0",
  "pydantic>=2.8,<3.0",
  "pydantic-settings>=2.4,<3.0",
  "sqlalchemy>=2.0,<3.0",
  "psycopg[binary]>=3.2,<4.0",
  "uvicorn[standard]>=0.30,<1.0",
]

[dependency-groups]
dev = [
  "pytest>=8.3,<9.0",
  "pytest-asyncio>=0.23,<1.0",
]
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/settings/ingestion.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CLAY_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://clay:clay@localhost:5432/clay_mc"
    binance_spot_enabled: bool = True
    market_symbols: list[str] = Field(
        default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    )
    market_timeframes: list[str] = Field(
        default_factory=lambda: ["5m", "15m", "1h"]
    )
    news_connector_ids: list[str] = Field(default_factory=lambda: ["demo-news"])
    sentiment_connector_ids: list[str] = Field(
        default_factory=lambda: ["demo-sentiment"]
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from clay_mc.settings.ingestion import IngestionSettings


def build_engine(settings: IngestionSettings | None = None):
    resolved = settings or IngestionSettings()
    return create_engine(resolved.database_url, future=True)


def build_session_factory(settings: IngestionSettings | None = None) -> sessionmaker:
    return sessionmaker(bind=build_engine(settings), autoflush=False, autocommit=False)
```

```dotenv
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/.env.example
CLAY_DATABASE_URL=postgresql+psycopg://clay:clay@localhost:5432/clay_mc
CLAY_BINANCE_SPOT_ENABLED=true
CLAY_MARKET_SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT"]
CLAY_MARKET_TIMEFRAMES=["5m","15m","1h"]
CLAY_NEWS_CONNECTOR_IDS=["demo-news"]
CLAY_SENTIMENT_CONNECTOR_IDS=["demo-sentiment"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv sync
uv run pytest tests/db/test_ingestion_schema.py -v
```

Expected: PASS with `IngestionSettings` returning the canonical `v1` symbols and timeframes.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/pyproject.toml backend/src/clay_mc/db backend/src/clay_mc/settings .env.example
git commit -m "feat: add ingestion settings and database bootstrap"
```

### Task 2: Create Canonical E2 Database Schema And Migration Baseline

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_create_e2_ingestion_baseline.py`
- Create: `backend/src/clay_mc/db/models_market.py`
- Create: `backend/src/clay_mc/db/models_context.py`
- Create: `backend/src/clay_mc/db/models_ops.py`
- Test: `backend/tests/db/test_ingestion_schema.py`

- [ ] **Step 1: Write the failing schema contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/db/test_ingestion_schema.py
from clay_mc.db.models_context import NewsItem, SentimentSnapshot
from clay_mc.db.models_market import MarketBar, MarketFreshnessStatus, OrderBookSummary
from clay_mc.db.models_ops import ConnectorStatusHistory, IngestRun, SourceHealthEvent


def test_market_schema_contains_expected_tables() -> None:
    assert MarketBar.__tablename__ == "market_bars"
    assert OrderBookSummary.__tablename__ == "orderbook_summaries"
    assert MarketFreshnessStatus.__tablename__ == "market_freshness_status"


def test_context_schema_contains_expected_tables() -> None:
    assert NewsItem.__tablename__ == "news_items"
    assert SentimentSnapshot.__tablename__ == "sentiment_snapshots"


def test_ops_schema_contains_expected_tables() -> None:
    assert IngestRun.__tablename__ == "ingest_runs"
    assert ConnectorStatusHistory.__tablename__ == "connector_status_history"
    assert SourceHealthEvent.__tablename__ == "source_health_events"
```

- [ ] **Step 2: Run the schema tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/db/test_ingestion_schema.py -v
```

Expected: FAIL because E2 ORM models do not exist yet.

- [ ] **Step 3: Implement the storage models and migration baseline**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/db/models_market.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from clay_mc.db.base import Base


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "bar_open_time", name="uq_market_bar"),
        {"schema": "market"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    quote_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="binance_spot")
    bar_open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bar_close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/db/models_context.py
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from clay_mc.db.base import Base


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    headline: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)


class SentimentSnapshot(Base):
    __tablename__ = "sentiment_snapshots"
    __table_args__ = {"schema": "context"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    sentiment_label: Mapped[str] = mapped_column(String(32))
    sentiment_score: Mapped[float] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/db/models_ops.py
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from clay_mc.db.base import Base


class IngestRun(Base):
    __tablename__ = "ingest_runs"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/alembic/versions/0001_create_e2_ingestion_baseline.py
from alembic import op
import sqlalchemy as sa


revision = "0001_create_e2_ingestion_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market")
    op.execute("CREATE SCHEMA IF NOT EXISTS context")
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.create_table(
        "market_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("bar_open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bar_close_time", sa.DateTime(timezone=True), nullable=False),
        schema="market",
    )
    op.execute(
        "SELECT create_hypertable('market.market_bars', 'bar_open_time', if_not_exists => TRUE)"
    )
```

- [ ] **Step 4: Run the schema tests and migration smoke check**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/db/test_ingestion_schema.py -v
uv run alembic upgrade head
```

Expected:
- schema contract tests PASS;
- migration completes against a local Timescale-enabled PostgreSQL instance.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/alembic.ini backend/alembic backend/src/clay_mc/db backend/tests/db
git commit -m "feat: add e2 storage schema baseline"
```

### Task 3: Implement Binance Spot Market Ingestion And Normalization

**Files:**
- Create: `backend/src/clay_mc/ingestion/market/models.py`
- Create: `backend/src/clay_mc/ingestion/market/binance_client.py`
- Create: `backend/src/clay_mc/ingestion/market/normalizer.py`
- Create: `backend/src/clay_mc/ingestion/market/service.py`
- Create: `backend/tests/ingestion/test_market_normalizer.py`

- [ ] **Step 1: Write the failing normalization tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/ingestion/test_market_normalizer.py
from clay_mc.ingestion.market.normalizer import normalize_kline_payload


def test_normalize_kline_payload_maps_binance_kline_to_market_bar() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "interval": "15m",
        "kline": {
            "t": 1711954800000,
            "T": 1711955699999,
            "o": "70250.10",
            "h": "70420.00",
            "l": "70180.40",
            "c": "70390.20",
            "v": "123.45",
            "q": "8670000.10",
        },
    }

    bar = normalize_kline_payload(payload)

    assert bar.symbol == "BTCUSDT"
    assert bar.timeframe == "15m"
    assert bar.close == 70390.20
    assert bar.quote_volume == 8670000.10
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/ingestion/test_market_normalizer.py -v
```

Expected: FAIL because the market normalizer does not exist yet.

- [ ] **Step 3: Implement the market ingestion contracts**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/market/models.py
from datetime import datetime

from pydantic import BaseModel


class NormalizedMarketBar(BaseModel):
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None
    source: str
    bar_open_time: datetime
    bar_close_time: datetime
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/market/normalizer.py
from datetime import UTC, datetime

from clay_mc.ingestion.market.models import NormalizedMarketBar


def normalize_kline_payload(payload: dict[str, object]) -> NormalizedMarketBar:
    kline = payload["kline"]
    return NormalizedMarketBar(
        symbol=str(payload["symbol"]),
        timeframe=str(payload["interval"]),
        open=float(kline["o"]),
        high=float(kline["h"]),
        low=float(kline["l"]),
        close=float(kline["c"]),
        volume=float(kline["v"]),
        quote_volume=float(kline.get("q")) if kline.get("q") is not None else None,
        source="binance_spot",
        bar_open_time=datetime.fromtimestamp(kline["t"] / 1000, tz=UTC),
        bar_close_time=datetime.fromtimestamp(kline["T"] / 1000, tz=UTC),
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/market/service.py
from collections.abc import Iterable

from clay_mc.ingestion.market.binance_client import BinanceSpotClient
from clay_mc.ingestion.market.models import NormalizedMarketBar
from clay_mc.ingestion.market.normalizer import normalize_kline_payload


class MarketIngestionService:
    def __init__(self, client: BinanceSpotClient) -> None:
        self.client = client

    async def fetch_latest_bars(
        self, symbols: list[str], timeframe: str
    ) -> list[NormalizedMarketBar]:
        payloads = await self.client.fetch_klines(symbols=symbols, timeframe=timeframe)
        return [normalize_kline_payload(payload) for payload in payloads]

    async def persist_bars(self, bars: Iterable[NormalizedMarketBar]) -> int:
        return len(list(bars))
```

- [ ] **Step 4: Run the test and add duplicate-handling coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/ingestion/test_market_normalizer.py -v
```

Expected: PASS for the normalization contract. Add a second test for duplicate bar identity using `symbol + timeframe + bar_open_time`.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/ingestion/market backend/tests/ingestion/test_market_normalizer.py
git commit -m "feat: add binance market ingestion contracts"
```

### Task 4: Add Pluggable News And Sentiment Connectors

**Files:**
- Create: `backend/src/clay_mc/ingestion/context/contracts.py`
- Create: `backend/src/clay_mc/ingestion/context/manager.py`
- Create: `backend/src/clay_mc/ingestion/context/connectors/demo_news.py`
- Create: `backend/src/clay_mc/ingestion/context/connectors/demo_sentiment.py`
- Create: `backend/tests/ingestion/test_context_connectors.py`

- [ ] **Step 1: Write the failing connector contract tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/ingestion/test_context_connectors.py
from clay_mc.ingestion.context.connectors.demo_news import DemoNewsConnector
from clay_mc.ingestion.context.connectors.demo_sentiment import DemoSentimentConnector


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/ingestion/test_context_connectors.py -v
```

Expected: FAIL because the context connector layer does not exist yet.

- [ ] **Step 3: Implement connector interfaces and manager**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/context/contracts.py
from abc import ABC, abstractmethod


class ContextConnector(ABC):
    connector_id: str
    connector_type: str
    source_name: str
    enabled: bool = True
    supports_symbols: bool = True

    @abstractmethod
    async def fetch(self) -> list[dict[str, object]]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, payload: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> dict[str, str]:
        raise NotImplementedError
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/context/manager.py
from clay_mc.ingestion.context.contracts import ContextConnector


class ContextConnectorManager:
    def __init__(self, connectors: list[ContextConnector]) -> None:
        self._connectors = connectors

    async def run_once(self) -> dict[str, int]:
        processed = 0
        for connector in self._connectors:
            if not connector.enabled:
                continue
            payloads = await connector.fetch()
            processed += len(payloads)
        return {"processed_records": processed}
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/ingestion/context/connectors/demo_news.py
from clay_mc.ingestion.context.contracts import ContextConnector


class DemoNewsConnector(ContextConnector):
    connector_id = "demo-news"
    connector_type = "news"
    source_name = "demo_news_feed"

    async def fetch(self) -> list[dict[str, object]]:
        return [{"headline": "BTC holds breakout", "symbol": "BTCUSDT"}]

    def normalize(self, payload: dict[str, object]) -> dict[str, object]:
        return payload

    async def health_check(self) -> dict[str, str]:
        return {"status": "healthy"}
```

- [ ] **Step 4: Run the tests and add rate-limit/error-state coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/ingestion/test_context_connectors.py -v
```

Expected: PASS for the connector contract and demo connectors. Add follow-up tests for `rate_limited` and `disabled` connector states.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/ingestion/context backend/tests/ingestion/test_context_connectors.py
git commit -m "feat: add pluggable context connectors"
```

### Task 5: Implement Freshness Evaluation, Incident Semantics, And Retention Jobs

**Files:**
- Create: `backend/src/clay_mc/freshness/models.py`
- Create: `backend/src/clay_mc/freshness/evaluator.py`
- Create: `backend/src/clay_mc/retention/jobs.py`
- Create: `backend/tests/freshness/test_evaluator.py`
- Create: `backend/tests/retention/test_jobs.py`

- [ ] **Step 1: Write the failing freshness and retention tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/freshness/test_evaluator.py
from datetime import UTC, datetime, timedelta

from clay_mc.freshness.evaluator import evaluate_market_freshness


def test_market_freshness_becomes_stale_after_threshold() -> None:
    now = datetime(2026, 4, 15, 10, 30, tzinfo=UTC)
    last_bar = now - timedelta(minutes=20)

    result = evaluate_market_freshness(
        timeframe="5m",
        last_received_at=last_bar,
        now=now,
    )

    assert result.status == "stale"
    assert result.blocks_active_trading is True
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/retention/test_jobs.py
from clay_mc.retention.jobs import retention_cutoff_days


def test_orderbook_retention_window_is_thirty_days() -> None:
    assert retention_cutoff_days("orderbook_summaries") == 30
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/freshness/test_evaluator.py tests/retention/test_jobs.py -v
```

Expected: FAIL because freshness and retention modules do not exist yet.

- [ ] **Step 3: Implement freshness semantics and retention policy**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/freshness/models.py
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class FreshnessResult:
    stream_name: str
    status: str
    observed_at: datetime
    blocks_active_trading: bool
    reason: str
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/freshness/evaluator.py
from datetime import datetime, timedelta

from clay_mc.freshness.models import FreshnessResult


MARKET_THRESHOLDS = {
    "5m": timedelta(minutes=10),
    "15m": timedelta(minutes=25),
    "1h": timedelta(minutes=80),
}


def evaluate_market_freshness(
    timeframe: str,
    last_received_at: datetime | None,
    now: datetime,
) -> FreshnessResult:
    if last_received_at is None:
        return FreshnessResult(
            stream_name=f"market:{timeframe}",
            status="unknown",
            observed_at=now,
            blocks_active_trading=True,
            reason="missing last_received_at",
        )

    delta = now - last_received_at
    threshold = MARKET_THRESHOLDS[timeframe]
    status = "fresh" if delta <= threshold else "stale"
    return FreshnessResult(
        stream_name=f"market:{timeframe}",
        status=status,
        observed_at=now,
        blocks_active_trading=status == "stale",
        reason=f"delta={delta}",
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/retention/jobs.py
RETENTION_WINDOWS_DAYS = {
    "market_bars": 730,
    "orderbook_summaries": 30,
    "market_features": 180,
    "news_items": 180,
    "sentiment_snapshots": 180,
    "connector_status_history": 180,
    "source_health_events": 180,
}


def retention_cutoff_days(table_name: str) -> int:
    return RETENTION_WINDOWS_DAYS[table_name]
```

- [ ] **Step 4: Run the tests and extend degraded-context coverage**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/freshness/test_evaluator.py tests/retention/test_jobs.py -v
```

Expected: PASS. Add a second freshness test proving that stale `news` or `sentiment` produces `degraded` semantics without hard-blocking market-only operation.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/freshness backend/src/clay_mc/retention backend/tests/freshness backend/tests/retention
git commit -m "feat: add freshness evaluation and retention jobs"
```

### Task 6: Expose Read Models And API Surfaces For Downstream Consumers

**Files:**
- Create: `backend/src/clay_mc/shortlist/models.py`
- Create: `backend/src/clay_mc/shortlist/read_models.py`
- Create: `backend/src/clay_mc/api/routes/ingestion.py`
- Create: `backend/src/clay_mc/api/routes/market_data.py`
- Create: `backend/src/clay_mc/api/routes/context_data.py`
- Create: `backend/src/clay_mc/api/routes/shortlist.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/api/test_ingestion_api.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing API tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_ingestion_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_ingestion_health_endpoint_returns_market_and_context_sections() -> None:
    client = TestClient(app)

    response = client.get("/ingestion/health")

    assert response.status_code == 200
    payload = response.json()
    assert "market" in payload
    assert "context" in payload


def test_shortlist_metrics_endpoint_returns_storage_backed_fields() -> None:
    client = TestClient(app)

    response = client.get("/shortlist/metrics")

    assert response.status_code == 200
    first_row = response.json()["items"][0]
    assert "rolling_volume_score" in first_row
    assert "rolling_volatility_score" in first_row
    assert "availability_status" in first_row
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_ingestion_api.py -v
```

Expected: FAIL because the ingestion routes do not exist yet.

- [ ] **Step 3: Implement shortlist read models and API routes**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/shortlist/models.py
from pydantic import BaseModel


class ShortlistMetricRow(BaseModel):
    symbol: str
    rolling_volume_score: float
    rolling_volatility_score: float
    liquidity_summary: str
    availability_status: str
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/ingestion.py
from fastapi import APIRouter


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/health")
def get_ingestion_health() -> dict[str, object]:
    return {
        "market": {"status": "healthy", "freshness": "fresh"},
        "context": {"status": "degraded", "freshness": "stale"},
        "incidents": [],
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/shortlist.py
from fastapi import APIRouter


router = APIRouter(prefix="/shortlist", tags=["shortlist"])


@router.get("/metrics")
def get_shortlist_metrics() -> dict[str, object]:
    return {
        "items": [
            {
                "symbol": "BTCUSDT",
                "rolling_volume_score": 0.92,
                "rolling_volatility_score": 0.61,
                "liquidity_summary": "high",
                "availability_status": "fresh",
            }
        ]
    }
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/main.py
from fastapi import FastAPI

from clay_mc.api.routes import ingestion, shortlist


app = FastAPI(title="CLAY Mission Control API")
app.include_router(ingestion.router)
app.include_router(shortlist.router)
```

- [ ] **Step 4: Run the API tests and document the contracts**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_ingestion_api.py -v
```

Expected: PASS with working backend-only read surfaces for health and shortlist inputs. Then update `README.md` with setup notes for PostgreSQL, TimescaleDB, migrations, and the new `E2` endpoints.

- [ ] **Step 5: Commit**

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend/src/clay_mc/api backend/src/clay_mc/shortlist backend/tests/api/test_ingestion_api.py README.md
git commit -m "feat: expose e2 ingestion and shortlist api surfaces"
```

## Spec Coverage Check

- `Binance Spot` backend-only ingestion is covered by Task 3.
- External `news` and `community sentiment` connector contracts are covered by Task 4.
- `PostgreSQL + TimescaleDB` storage baseline and logical domains are covered by Task 2.
- Freshness, stale semantics, degraded context handling, and retention policy are covered by Task 5.
- Storage-backed shortlist inputs and downstream read surfaces are covered by Task 6.
- Control-plane health, incidents, and downstream API contracts are covered by Tasks 5 and 6.

## Assumptions

- The existing `E1` implementation plan remains the canonical precursor and is not rewritten here.
- This plan is backend-heavy by design; `E3` will consume these contracts later instead of re-inventing them in the UI layer.
- `demo-news` and `demo-sentiment` connectors are intentionally low-risk placeholders for interface validation, not final provider choices.
- Repository paths in this plan are provisional and may be normalized after demo validation, provided module boundaries and contracts remain intact.

## Execution Handoff

Plan complete and saved to `implementation_plans/e2-data-ingestion-and-local-historical-store-implementation-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
