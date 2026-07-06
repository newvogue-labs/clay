---
date: 2026-06-02
type: research
applies-to: [clay, python, httpx, async, code-review, testing]
status: ratified (B4.5 framing)
tags: [httpx, async-with, response-lifecycle, smell-vs-bug, test-framing, review]
---

# obs-2026-06-02-004: httpx non-streaming `response.json()` after `async with` — smell, not live bug

## Проблема / Контекст

При review `binance_client.py:36-44` (Wave B B4.5) — `response.raise_for_status()` и `response.json()` вызывались **после** `async with httpx.AsyncClient() as client:`. Контринтуитивно выглядит как race / lifecycle bug. **Не** является таковым для non-streaming запросов — но framing "это баг, давайте чинить и писать regression test" был бы неверным и вёл бы к brittle monkey-patch testing.

## Физика httpx (Emma recon)

Для **non-streaming** `await client.get(...)` httpx **полностью читает и буферизует `.content` ДО возврата** из `get()`. Конкретно:

- `AsyncClient.__aexit__` → `aclose()` → закрывает connection pool/transport
- Но `.content` (тело ответа) уже в памяти к моменту `__aexit__` — **не зависит** от живого соединения
- `response.json()` / `raise_for_status()` после `async with` читают из **буфера**, не из stream
- Гарантировано на всех версиях httpx (≥0.20+)

**ReadError / ResponseNotRead** ловятся **только** при `client.stream(...)` (явный streaming API). В `binance_client.py` его нет — поэтому багнутый код работает корректно на runtime.

## Smell vs. live bug — framing

| Категория | Live bug | Smell (наш случай) |
| --- | --- | --- |
| Runtime effect | ❌ данные теряются / ломаются | ✅ работает, но хрупко |
| Test can fail on buggy code | ✅ regression test возможен | ❌ regression test **не существует** |
| Migration risk | N/A | ⚠️ упадёт при `client.stream()` миграции |
| Fix urgency | High | Low (cheap, future-proof, делаем заодно) |
| Test value | Regression guard | Contract pin + first coverage |

**`binance_client.py:36-44` — smell, не live data-corruption.** Fix всё равно делаем: дёшев, future-proof, чистит HTTP-путь перед B5 (IngestionCycleJob → hot loop на 60s interval).

## Следствие для теста (ключевое)

Раз `.json()` работает post-close по контракту httpx — **ни injected-, ни monkey-patch-тест не упадёт на багнутом коде**. Честного regression-теста, который "доказывает баг", здесь **не существует**.

**Test ценен как:**
1. **First coverage** `BinanceSpotClient` (было 0 — `MarketIngestionService` test path использует `FakeBinanceClient` short-circuit)
2. **Contract pin** для парсинга klines (что именно возвращается из `/api/v3/klines`)

**НЕ** как regression guard для smell-а. Monkey-patch option для прямого покрытия else-ветки — отклонён Emma: brittle + доказательно бесполезен.

## Why

Recon пришёл от Emma — она уточнила физику httpx, что изменило framing и test-стратегию. Без этой проверки был бы соблазн либо (a) oversell как критический баг, либо (b) написать brittle monkey-patch test, который "кажется regression guard'ом" но не ловит ничего.

## How to apply

**При review любого httpx async кода в Clay / других проектах:**

1. **Сначала** проверь: `client.get(...)` non-streaming ИЛИ `client.stream(...)`?
   - non-streaming → `.content` буферизуется до возврата, `response.json()` post-close **OK по контракту**
   - stream → body читается лениво, `response.json()` post-close **может упасть** (ReadError/ResponseNotRead)
2. **Если non-streaming** — framing: smell (future-proof), не bug. Fix optional, дешёвый.
3. **Если stream** — framing: реальный bug. Fix обязателен, regression test возможен.
4. **Если test "не падает на багнутом коде"** — это **НЕ** regression test, это contract pin. Ценность другая (coverage + contract), не ловит регрессии.

**Чего НЕ делать:**

- ❌ Не oversell "response after async with" как critical bug без проверки stream/non-stream
- ❌ Не писать monkey-patch test, который "имитирует close-then-read" — для non-streaming это проверяет **контракт httpx**, не код
- ❌ Не пропускать docstring в test, объясняющий **что именно** тест покрывает (coverage vs regression) — future maintainer не должен пытаться "починить тест чтобы он ловил баг" (там нечего чинить)

## Carry-forward

- **B5 (IngestionCycleJob) pre-flight recon:** применять ту же дихотомию (stream vs. non-stream) к любым HTTP-зависимым сервисам, которые планируется дёргать в scheduler-job.
- **Clay v2 candidate:** `lifespan-owned httpx.AsyncClient` для `binance_client` — else-ветка создаёт новый `AsyncClient()` на каждый вызов. Под B5 (60s interval = 1440 calls/day) расточительно. Кандидат на отдельный slice после B6.
- **Other projects:** эта framing'овская проверка generic для **любого** async HTTP клиента (httpx, aiohttp, requests-futures) — всегда спрашивай "streaming или buffered?" перед классификацией как bug/smell.
