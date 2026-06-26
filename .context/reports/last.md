# Отчёт: сессия 2026-06-26 — S-EGRESS-RECON-1 (read-only egress dossie)

## Что сделано

### S-EGRESS-RECON-1 — Testnet reachability + non-US egress map + integration point (ГОТОВ ✅)

#### Testnet reachability (активные проверки)

- **Текущий egress:** Paris, France (`83.136.209.168`, AS400897 PETROSKY CLOUD LLC) — EU, non-US.
- **Spot testnet:** `testnet.binance.vision` → HTTP 200 ping, real OHLCV klines, exchangeInfo доступен
- **Futures testnet:** `testnet.binancefuture.com` (dapi + eapi) → HTTP 200
- **Auth gate (negative test):** unauthenticated /api/v3/account → code -1102 (корректная защита)
- **451:** не обнаружен с текущего egress
- **Production binance.com** тоже HTTP 200 из Paris

#### Non-US egress опции

| Вариант | Пример | Стоимость | Сложность | Примечание |
|---------|--------|-----------|-----------|-------------|
| VPS | Hetzner DE/FI | €4-8/мес | Низкая | Recommended для production |
| VPS | OVHcloud FR/DE | €3-7/мес | Низкая | Альтернатива Hetzner |
| Proxy | Cloudflare Workers | Free | Низкая | Только testnet, не для prod per ToS |
| VPN | Mullvad/IVPN | €5/мес | Низкая | Быстрый старт, IP-пулы иногда флагаются |

#### Интеграция с существующим кодом (ADR-008, Wave E3)

- Точка подключения: `CLAY_BINANCE_BASE_URL` → `ExchangeConfig.base_url` → `BinanceSpotClient`
- **0 кода:** только env var переключатель
- **Не трогаем:** Protocol shape, NormalizedMarketBar, symbol mapping, freshness, rate limiter, factory signature
- Hard real-money gate (RV8) — не реализован, планируется отдельный ADR (ExecutionClient Protocol + override + audit)

### Изменённые файлы

| Файл | Описание |
|------|----------|
| `docs/mission-control/egress-recon/S-EGRESS-RECON-1.md` | Read-only досье (новый) |

## Итог

**HEAD `e663019` (S-EGRESS-RECON-1). 0 кода, 0 ключей, 0 side-effects.**

Testnet reachable из текущего Paris egress. Рекомендация: **testnet-first** (zero friction), потом Hetzner VPS для non-US, отдельный ADR на real-money execution.
