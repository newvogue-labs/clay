# ADR-032 Addendum: Bybit Environment → Endpoint Mapping

> Date: 2026-07-24
> Status: Accepted
> Related: ADR-032 (adapter-level enumerations), F-D12-10 smoke

## Context

Bybit adapter (`bybit.py`) now supports three environment modes. `enable_demo_trading` and `set_sandbox_mode` are **mutually exclusive** in ccxt — calling both causes undefined behavior.

## Environment → Endpoint Table

| `Environment` | ccxt call | Bybit endpoint | Notes |
|---|---|---|---|
| `TESTNET` | `set_sandbox_mode(True)` | `api-testnet.bybit.com` | Sandbox/testnet keys |
| `DEMO` | `enable_demo_trading(True)` | `api-demo.bybit.com` | Demo trading keys (`CLAY_BYBIT_DEMO_API_KEY` / `_SECRET`) |
| `PRODUCTION` | _(no-op)_ | `api.bybit.com` | Live trading |
| `PAPER` | _(raises ConfigError)_ | — | Unsupported by Bybit adapter |

## Fail-closed guard

Any `Environment` value outside `{TESTNET, DEMO, PRODUCTION}` raises `ConfigError` with message:

```
environment <value> not supported by Bybit adapter
```

**Lead (not fixed in this slice):** The same fail-open latent exists in `ccxt_base` / `binance` — `Environment.PAPER` silently falls through to production client. Flagged for future attention.

## Demo credentials

Demo trading credentials are supplied exclusively through environment variables:

| Variable | Description |
|---|---|
| `CLAY_BYBIT_DEMO_API_KEY` | Bybit demo trading API key |
| `CLAY_BYBIT_DEMO_API_SECRET` | Bybit demo trading API secret |

**Never** committed to code, TOML, or logs.

## Smoke validation

`scripts/smoke_bybit_demo.py` validates demo reachability, auth, and optionally order round-trip. Run manually by operator — not part of CI.
