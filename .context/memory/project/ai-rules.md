---
id: project-clay-ai-rules
name: Clay AI integration rules (STRICT)
description: 4 железных правила интеграции AI в Clay. Нарушать нельзя.
type: project
tags: [ai, integration, security, architecture]
created: 2026-06-01
updated: 2026-06-01
---

**Контекст:** Восстановлено из `CLAUDE.md.bak` (intelligence v1).

**Правила (STRICT):**

### 1. Backend-only AI
Никаких прямых вызовов AI-провайдеров из Frontend.
Используется **Clay Provider Abstraction Layer** на backend.

### 2. Stream Normalization
Все AI-стримы проходят через **internal SSE event format**.
Frontend не получает сырые стримы от провайдеров.

### 3. No WebSockets by default
Используем **SSE** для live updates и signals.
WebSocket запрещён policy.

### 4. Data Integrity
AI = **synthesis layer**.
Market Data и Risk Rules = **ground truth**.
AI не подменяет рыночные данные и риск-правила.

**Why:** Безопасность (API keys не утекают во frontend), вендор-agnostic (легко менять провайдера), предсказуемость (формат стрима стабилен), честность (AI не врёт про рынок).

**How to apply:** Любое AI-related изменение должно проходить через эти правила. Нарушение = блокер в code review.
