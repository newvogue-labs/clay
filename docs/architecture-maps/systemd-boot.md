# D5 — Systemd boot-chain (as-deployed)

```mermaid
graph TD
    subgraph "Host boot chain"
        TS["clay_timescaledb<br/>Podman container (compose.yaml)<br/>Postgres / TimescaleDB :5433"]
        LL["clay-litellm.service<br/>system unit<br/>LiteLLM gateway :4000"]
        BK["clay-backend.service<br/>system unit<br/>api (uvicorn) :8000 + scheduler"]
    end

    subgraph "Dependencies"
        TS -.->|no After=/Requires= documented| LL
        LL -->|"After=network-online.target"| BK
    end

    BK -->|"6 job types incl. AIAgentCycleJob"| D3

    D3["D3 — Trading Cycle<br/>(AIAgentCycleJob, flag-gated)"]

    style TS stroke:#d93,stroke-dasharray: 5 5
```

> **Note:** `clay_timescaledb` runs via `compose.yaml` (in-repo, `restart: unless-stopped`). Systemd units: `deploy/systemd/` (in-repo, as-deployed copy, no secrets inline). Dashed border = managed outside systemd.
