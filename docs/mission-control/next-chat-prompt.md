# CLAY Next Codex Chat Prompt

```text
Прочитай handoff-файл:
/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/handoff-2026-03-30.md

Используй для этой задачи planning/research skills с приоритетом:
$create-plan, $brainstorming, $writing-plans, $concise-planning, $ai-agents-architect, $rag-engineer, $agent-evaluation

Примечание: `$create-plan` здесь локальный кастомный skill, установленный в user-level Codex skills.

Нужно составить подробный и тщательно выверенный инженерный план системы CLAY Trading System.
Важно: сейчас не писать код и не переходить к реализации.

Контекст:
- нужна независимая trading architecture;
- OpenClaw только как optional sidecar/control-plane, не core;
- базовый подход: hybrid alpha;
- книги и документация идут как research/RAG/policy layer, а не как прямой источник торгового сигнала;
- пользователь сам совершает сделки, система дает аналитику, прогнозы, рекомендации и сигналы.

Используй также эти локальные материалы:
- /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_TRADING_SYSTEM.docx
- /home/emma/Documents/Obsidian/CachyOS/Trading/Mission Control.md
- /home/emma/Applications/openclaw

И эти reference repos:
- openai/skills
- sickn33/antigravity-awesome-skills
- obra/superpowers
- paperswithbacktest/awesome-systematic-trading
- TauricResearch/TradingAgents
- ccxt/ccxt
- QuantConnect/Lean

На выходе нужен именно инженерный план: архитектура, подсистемы, data flow, роли агентов, risk/eval/latency/observability, этапы реализации, но без написания кода.
```
