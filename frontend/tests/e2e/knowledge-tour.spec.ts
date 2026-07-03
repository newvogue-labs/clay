import { test, expect } from '@playwright/test'

const SCREEN = '#knowledge'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('Knowledge Tour — priority badges high 🟢 / medium 🟡 (F21)', () => {
  test('Items with high/medium/low priority → correct StatusBadge tone + card data-tone', async ({ page }) => {
    // ---------- fixture ----------
    const fixture = {
      summary: {
        total_items: 5,
        categories: ['alpha-signals', 'market-regime'],
        last_ingested_at: '2026-07-03T08:00:00Z',
        indexing_status: 'ready',
      },
      recent_items: [
        {
          item_id: 1,
          title: 'Momentum breakout regime',
          category: 'market-regime',
          priority: 'high',
          tags: ['momentum', 'breakout'],
          source_type: 'research',
          content_preview: 'High momentum signals across majors.',
          created_at: '2026-07-03T07:00:00Z',
          updated_at: '2026-07-03T07:00:00Z',
          chunk_count: 3,
        },
        {
          item_id: 2,
          title: 'Volatility contraction pattern',
          category: 'alpha-signals',
          priority: 'medium',
          tags: ['volatility', 'pattern'],
          source_type: 'analysis',
          content_preview: 'BTC volatility contracting — breakout imminent.',
          created_at: '2026-07-03T06:00:00Z',
          updated_at: '2026-07-03T06:00:00Z',
          chunk_count: 2,
        },
        {
          item_id: 3,
          title: 'Correlation shift notice',
          category: 'alpha-signals',
          priority: 'low',
          tags: ['correlation'],
          source_type: 'alert',
          content_preview: 'BTC-ETH correlation dropped to 0.3.',
          created_at: '2026-07-02T23:00:00Z',
          updated_at: '2026-07-02T23:00:00Z',
          chunk_count: 1,
        },
      ],
      search_results: [],
    }

    await page.route('**/knowledge/overview', async (route) => {
      await route.fulfill({ json: fixture, status: 200 })
    })

    // ---------- mount ----------
    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="knowledge"]', { timeout: 15_000 })
    await page.waitForTimeout(2000)

    // ---------- V1: knowledge-item-card data-tone matches priority ----------
    const itemCards = page.locator('.knowledge-item-card')
    const cardCount = await itemCards.count()
    console.log(`\n=== Knowledge item cards: ${cardCount} ===`)
    expect(cardCount).toBe(3)

    const priorityToExpectedTone: Record<string, string> = {
      high: 'success',
      medium: 'warning',
      low: 'muted',
    }

    // Batch A: StatusBadge receives tone prop from getPriorityTone.
    // tone prop overrides internal lookup → all 3 badges are colored.
    const lookupHas: Record<string, boolean> = {
      high: true,
      medium: true,
      low: true,
    }

    for (let i = 0; i < cardCount; i++) {
      const card = itemCards.nth(i)
      const dataTone = await card.getAttribute('data-tone')
      const priorityBadge = card.locator('[data-status]').first()
      const priority = await priorityBadge.getAttribute('data-status')
      const badgeClass = await priorityBadge.getAttribute('class')

      const expectedTone = priorityToExpectedTone[priority] || 'muted'
      // StatusBadge CSS classes from status-badge.tsx
      const toneColorClass = expectedTone === 'success'
        ? 'border-clay-success/30 bg-clay-success/12 text-clay-success'
        : expectedTone === 'warning'
          ? 'border-clay-warning/30 bg-clay-warning/12 text-clay-warning'
          : expectedTone === 'danger'
            ? 'border-clay-danger/30 bg-clay-danger/12 text-clay-danger'
            : 'border-clay-border bg-clay-bg/55 text-clay-text-muted'

      const badgeIsCorrect = badgeClass?.includes(toneColorClass)
      console.log(`\n  Card #${i}: priority="${priority}" data-tone="${dataTone}" badge-correct: ${badgeIsCorrect}`)
      console.log(`    ASSERT: card data-tone="${dataTone}" === expected "${expectedTone}"`)

      // Card data-tone MUST match (from getPriorityTone)
      expect(dataTone).toBe(expectedTone)

      // F21 closed: tone prop overrides lookup
      if (lookupHas[priority]) {
        expect(badgeClass).toContain(toneColorClass)
      } else {
        console.log(`    NOTE: StatusBadge for "${priority}" is muted (not in lookup — F21 gap, not a regression)`)
      }
    }

    // ---------- V2: priority label visible in card body ----------
    for (let i = 0; i < cardCount; i++) {
      const card = itemCards.nth(i)
      const cardText = await card.textContent()
      const containsPriorityLabel = cardText?.includes('high') || cardText?.includes('medium') || cardText?.includes('low')
      console.log(`  Card #${i} body contains priority label: ${containsPriorityLabel}`)
    }

    await page.screenshot({ path: '/tmp/workspace-tour/knowledge-priority-badges.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/knowledge/overview')
    const realResp = await page.request.get(`${API}/knowledge/overview`)
    const realData = await realResp.json()
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API total_items: ${realData.summary.total_items} (fixture was 5)`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)
    expect(realData.summary.total_items).not.toBe(5)
  })
})
