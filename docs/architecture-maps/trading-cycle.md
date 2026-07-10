---
tags:
  - architecture
  - execution
  - signals
---

# D3 — Trading Cycle (sequence)

```mermaid
sequenceDiagram
    participant S as scheduler<br/>(AIAgentCycleJob)
    participant AC as ai_control
    participant SE as signal_engine
    participant K as knowledge<br/>(advisory‑only)
    participant R as RoutingModelClient
    participant DB as db

    Note over S,R: Scheduled tick (CLAY_SCHEDULER_AI_AGENT_ENABLED, opt‑in)
    S->>AC: _build_snapshot()
    AC-->>S: AIControlSnapshot
    S->>SE: _render_signals_safe()
    SE-->>S: signals (EV, Kelly, rank)
    S->>K: _retrieve_advisory_cards()
    Note over K: M278: advisory data, NOT instructions
    K-->>S: scored cards (≤15, ≤2000 tokens)
    S->>S: _render_context() → 7‑section plain‑text
    S->>R: AgentRunner.run_agent(role_id, context)
    alt local route
        R-->>R: OllamaNativeClient (127.0.0.1:11434)
    else cloud route
        R-->>R: LiteLLMModelClient (127.0.0.1:4000)
    end
    R-->>S: agent response text
    S->>DB: persist_success() (ops.ai_agent_runs)

    Note over S,DB: ═══ Cycle does NOT auto‑execute ═══
```

### Execution-gate fragment

> The trading cycle **prepares** a decision but does **not** arm execution.
> Live mode is a **stub** — operator must manually override via `request → confirm → revoke` cycle.

```mermaid
sequenceDiagram
    participant OP as Operator
    participant OVS as OverrideService
    participant EX as execution<br/>(ccxt → Binance)

    OP->>OVS: POST /override/request (actor, reason)
    OVS-->>OP: override_id (status=pending)
    OP->>OVS: POST /override/confirm (ttl=1h)
    OVS->>OVS: is_live_eligible()
    OVS-->>OP: confirmed
    OP->>EX: binance order<br/>(CLAY_EXECUTION_MODE=testnet)
    Note over EX: live = NotImplemented<br/>(factory.py LiveExecutionClient stub)
```
