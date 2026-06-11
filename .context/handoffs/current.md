---
date: 2026-06-11
from: Emma
status: 5b-iii CLOSED целиком. 3 cloud × полный цикл.
pytests: "441"
pyright_src: "33 (baseline)"
ruff: "13 (src baseline)"
live_db: "5432 — НЕ ТРОГАТЬ"
podman_db: "5433 — TS2.27.1 (0015 head) — inet_server_port()=5432 (Podman mapping)"
tun: "UP — UK (YottaSrc) exit"
killswitch: "active (71 reject pkts)"
scheduler: "ON — CLAY_SCHEDULER_ENABLED=true"
litellm_models: "5 — gemma4-e2b, local-ollama, gemini-2.5-flash, minimax-m3, gemini-3.1-flash-lite"
model_registry: "7 — minimax-m3, openai-gpt-5.4-mini, anthropic-claude-sonnet-4.5, gemini-2.5-flash, forecast-lite-v1, gemini-3.1-flash-lite, gemma4:e2b-it-qat"
---

# Deploy-трек — 5b-iii CLOSED

## Коммиты (HEAD `73b59ac`)

| SHA | Message |
|-----|---------|
| `73b59ac` | feat(ai-control): add gemini-3.1-flash-lite registry, assign forecast-model (5b-iii.5b) |
| `6969224` | docs(mission-control): dual-transport routing, provider policy, quota runbook (5b-iii) |
| `bbf6623` | feat(ai-control): add minimax-m3 cloud model, assign chief-agent (5b-iii.4b) |
| `a4489ac` | feat(ai): LiteLLM cloud ModelClient + per-call transport routing via model registry |
| `5e2f5b8` | docs(context): update state.md + reports/last.md for 5b-iii.1 |
| `c31c782` | docs(ai): runbook-004 dual-transport + ADR-009 addendum + litellm config examples |

## Закрыто (сессия)

- **5b-iii.1:** LiteLLMModelClient + RoutingModelClient ✅ `a4489ac`
- **5b-iii.2:** host-config Gemini boundary-live ✅ 0 коммитов
- **5b-iii.3:** attended smoke (429 Gemini RPD) ❌ STOP, не retry
- **5b-iii.4a:** TokenRouter/MiniMax-M3 host-config ✅ 0 коммитов
- **5b-iii.4b:** minimax-m3 in registry, chief-agent назначен ✅ `bbf6623`
- **5b-iii.4c:** live-smoke chief-agent→minimax-m3 ✅ 2 цикла, content_len=1115/1718, error=NULL
- **5b-iii-docs:** runbook, ADR addendum, config examples, backlog ✅ `6969224`
- **5b-iii.5a:** Gemini 3.1 Flash Lite host-config ✅ 0 коммитов (0.69s — рекорд шлюза)
- **5b-iii.5b:** gemini-3.1-flash-lite в реестр + forecast-model переназначение ✅ `73b59ac`
- **5b-iii.5c:** attended smoke forecast-model полный цикл ✅ 2 цикла, content=283/317, error=NULL
- **5b-iii целиком ЗАКРЫТ:** 3 cloud × полный цикл, dual-transport live на обоих плечах

## Открыто / следующий

- **5c (subagents):** recon-слайс. Субагенты: market-scanner, news-sentiment на demo-провайдерах
- **provider pool free-tier:** Emma → список источников → recon → приоритезация
- **FOOTGUN fix IngestionSettings:** env_file или fail-loud на live 5432
- **Gemini 3.1 Flash Lite .5b + .5c:** model in registry + forecast-model assignment + attended smoke

## Ключевые решения сессии

1. **RoutingModelClient per-call** — не static select в lifespan. Смена assignment в рантайме без stale-клиента.
2. **3 cloud-провайдера live:** TokenRouter/MiniMax, Gemini 2.5 Flash, Gemini 3.1 Flash Lite. В шлюзе 5 моделей.
3. **placeholder openai-gpt-5.4 удалён** — chief-agent → minimax-m3 штатно (0 bypass)
4. **FOOTGUN IngestionSettings:** pydantic-settings без env_file → bootstrap дефолтит в live 5432. Явный CLAY_DATABASE_URL обязателен в команде запуска.
5. **Free-tier политика:** 429 = STOP, 0 retries. Пробник перед прогоном. Бюджет беречь.
6. **Provider policy (Emma):** demo = любые бесплатные провайдеры но строго через шлюз + TUN + kill-switch. Real-money = только официальные платные.
