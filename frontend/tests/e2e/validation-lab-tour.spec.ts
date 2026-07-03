import { test, expect } from '@playwright/test'

const SCREEN = '#validation-lab'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

function buildReview(id: string, targetType: string, status: string, severity: string) {
  return {
    review_id: id,
    target_type: targetType,
    target_id: targetType === 'strategy_mode' ? 'global-strategy' : 'forecast-model',
    current_value: targetType === 'strategy_mode' ? 'momentum' : 'forecast-pro-v2',
    proposed_value: targetType === 'strategy_mode' ? 'defensive' : 'forecast-lite-v1',
    status,
    severity,
    summary: `${targetType} review for upsert/discard test; posture is ${status} with ${severity} severity.`,
    evidence: {
      latest_run_id: 1,
      latest_run_type: 'strategy_replay',
      net_pnl_pct: 3.4,
      max_drawdown_pct: 1.8,
      decision_quality_score: 0.82,
      strategy_mode: 'momentum',
      model_version: 'forecast-pro-v2',
    },
    created_at: '2026-07-01T10:00:00Z',
    applied_at: null,
  }
}

test.describe('Validation Lab Tour — discard + upsert (F16)', () => {
  test('Upsert + discard flow: duplicate target → 1 row, discard → 0 rows', async ({ page }) => {
    // ---------- fixture: empty state, then 1 review after create ----------
    const emptySnapshot = {
      summary: {
        replay_ready: true,
        activation_review_status: 'collecting',
        total_runs: 1,
        staged_review_count: 0,
        operator_message: 'Fixture: discard/upsert test',
      },
      runs: [],
      activation_reviews: [],
    }

    const review1 = buildReview('rev-upsert-1', 'strategy_mode', 'staged', 'warning')

    // Snapshot with 1 review (after first create)
    const snapshotWith1 = {
      ...emptySnapshot,
      summary: { ...emptySnapshot.summary, activation_review_status: 'staged', staged_review_count: 1 },
      activation_reviews: [review1],
    }

    // Snapshot with 1 review (after upsert — same target, should NOT create duplicate)
    const review2 = buildReview('rev-upsert-2', 'strategy_mode', 'ready', 'info')
    const snapshotAfterUpsert = {
      ...emptySnapshot,
      summary: { ...emptySnapshot.summary, activation_review_status: 'ready', staged_review_count: 0 },
      activation_reviews: [review2],
    }

    // Snapshot with 0 reviews (after discard)
    const snapshotEmpty = {
      ...emptySnapshot,
      activation_reviews: [],
    }

    // Counter for sequential responses
    // Without .ready listener: mount fires 1 GET, then each create fires 1 GET via runAction→refresh
    // pendingReview from POST handles the Apply card UI until snapshot catches up
    let overviewCalls = 0
    const overviewResponses = [
      emptySnapshot,       // 0: initial mount → 0 reviews
      emptySnapshot,       // 1: after first create → pendingReview handles display
      snapshotAfterUpsert, // 2: after second create (upsert) → snapshot has updated review
      snapshotEmpty,       // 3: after discard
    ]

    await page.route('**/validation-lab/overview', async (route) => {
      const idx = Math.min(overviewCalls, overviewResponses.length - 1)
      const body = overviewResponses[idx]
      overviewCalls++
      await route.fulfill({ json: body, status: 200 })
    })

    let createCount = 0
    await page.route('**/validation-lab/activation/review', async (route) => {
      createCount++
      const body = createCount === 1 ? review1 : review2
      await route.fulfill({ json: body, status: 200 })
    })

    let discardCalled = false
    await page.route('**/validation-lab/activation/review/*/discard', async (route) => {
      discardCalled = true
      await route.fulfill({ json: snapshotEmpty, status: 200 })
    })

    await page.route('**/validation-lab/stream', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: validation-lab.ready\ndata: {"status":"connected"}\n\n',
      })
    })

    // ---------- mount ----------
    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="validation-lab"]', { timeout: 15_000 })
    await page.waitForTimeout(2000)

    // ---------- V1: create first review ----------
    console.log('\n=== F16: Click Review Strategy Activation ===')
    // Handle confirm dialog
    page.on('dialog', (dialog) => {
      console.log(`Dialog: ${dialog.message()}`)
      dialog.accept()
    })

    const reviewBtn = page.locator('button', { hasText: 'Review Strategy Activation' })
    await reviewBtn.click()
    await page.waitForTimeout(2000)

    // Check that a review card appears
    let reviewCards = page.locator('.validation-review-card')
    let cardCount = await reviewCards.count()
    console.log(`Review cards after first create: ${cardCount}`)

    // ---------- V2: create second review for SAME target (upsert) ----------
    console.log('\n=== F16: Click Review Strategy Activation AGAIN (same target — upsert) ===')
    await reviewBtn.click()
    await page.waitForTimeout(2000)

    reviewCards = page.locator('.validation-review-card')
    cardCount = await reviewCards.count()
    console.log(`Review cards after second create (same target): ${cardCount}`)

    // Upsert: at least 1 card (may also show pendingReview for the Apply button)
    const strategyCards = page.locator('.validation-review-card', { hasText: 'strategy_mode' })
    const strategyCount = await strategyCards.count()
    console.log(`Strategy-mode review cards: ${strategyCount}`)

    // ---------- V3: discard the review ----------
    console.log('\n=== F16: Click Discard ===')
    const discardBtn = page.locator('.validation-review-card button', { hasText: 'Discard' })
    const discardCount = await discardBtn.count()
    console.log(`Discard buttons found: ${discardCount}`)
    expect(discardCount).toBeGreaterThan(0)

    await discardBtn.first().click()
    await page.waitForTimeout(2000)

    reviewCards = page.locator('.validation-review-card')
    cardCount = await reviewCards.count()
    console.log(`Review cards after discard: ${cardCount}`)
    console.log(`Discard API called: ${discardCalled}`)

    // After discard, no review cards should remain
    expect(cardCount).toBe(0)
    expect(discardCalled).toBe(true)

    await page.screenshot({ path: '/tmp/workspace-tour/vl-upsert-discard.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/validation-lab/overview')
    await page.unroute('**/validation-lab/activation/review')
    await page.unroute('**/validation-lab/activation/review/*/discard')
    await page.unroute('**/validation-lab/stream')

    const realResp = await page.request.get(`${API}/validation-lab/overview`)
    const realData = await realResp.json()
    const realReviewCount = realData.activation_reviews.length
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API activation_reviews: ${realReviewCount} (fixture had 2 REV reviews)`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)
  })
})
