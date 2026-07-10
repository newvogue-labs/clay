---
tags:
  - architecture
---

# Architecture Maps

## D1 — System Context (C4)

```mermaid
graph TB
    Clay("Clay System")

    Operator["👤 Operator"] ---|"CLI / browser (:5173)"| Clay
    Clay ---|"REST/WS (ccxt)"| Binance["Binance Testnet<br/>testnet.binance.vision"]
    Clay ---|"OpenAI-compat chat"| LiteLLM["LiteLLM Gateway<br/>127.0.0.1:4000"]
    Clay ---|"SQL (psycopg)"| PG[("PostgreSQL / TimescaleDB<br/>127.0.0.1:5433")]
    Clay ---|"Notion API"| Notion["Notion Mirror<br/>notion.com"]
    Vault[("Knowledge Vault<br/>clay-knowledge")] ---|"sync.py HTTP"| Clay
```

## D2 — Module Map (container-level)

```mermaid
graph TB
    subgraph "Clay Backend (container-level DI graph)"
        API["api: FastAPI<br/>port :8000"]
        Scheduler["scheduler: APScheduler<br/>6 job types"]
        AIControl["ai_control: Agent Runner<br/>routing → local/cloud LLM"]
        Knowledge["knowledge: #knowledge<br/>CRUD + token search"]
        Signal["signal_engine<br/>EV → Kelly → rank"]
        Execution["execution: Order Gate<br/>dry_run │ testnet │ live﹡"]
        DB[("db: SQLAlchemy<br/>Postgres / TimescaleDB")]
    end

    API -->|"routes → services"| AIControl
    API -->|"routes → services"| Knowledge
    API -->|"routes → services"| Signal
    API -->|"routes → services"| Execution

    Scheduler -->|"background jobs"| AIControl
    Scheduler -->|"ingest"| Knowledge

    AIControl -.->|"advisory (M278)"| Knowledge
    AIControl -->|"reads"| Signal

    Knowledge --> DB
    Signal --> DB
    Execution --> DB
    API --> DB
```

> **Примечания.** `bootstrap.py` производит DI-сборку всех сервисов при import time — стрелки не показаны для читаемости. `live` execution — stub (NotImplemented), operator override required (manual `request → confirm → revoke`).
