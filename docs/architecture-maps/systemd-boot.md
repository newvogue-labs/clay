# D5 — Systemd boot-chain (as-deployed)

!!! warning "Repo-gap: as-deployed ≠ in-repo"

    - `clay-backend.service` — **only on host**, `.service` file **not in repository**.
    - Source of truth for this diagram: `state.md` (D4 systemd setup) and `runbook-004`.
    - `clay_timescaledb` — podman container **without restart-policy** (backlog item).
    - `deploy/litellm/clay-litellm.service` — template (emeritus user-unit, superseded by system unit).

```mermaid
graph TD
    subgraph "Host boot chain"
        TS["clay_timescaledb<br/>Podman container<br/>Postgres / TimescaleDB :5433"]
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
    style BK stroke:#d93,stroke-dasharray: 5 5
```

> **Legend:** dashed border = not in repo / documented gap.
