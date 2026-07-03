import { test, expect } from '@playwright/test'

const SCREEN = '#session-control'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('Session Control Tour — close-review (F12) + SSE (F13)', () => {
  test('Close review: button visible in review state → transitions to idle', async ({ page }) => {
    // ---------- fixture: lifecycle in review ----------
    const fixture = {
      preflight: {
        status: 'pass',
        blocking_reason: null,
        checks: [],
      },
      briefing: {
        shortlist: [],
        market_context: 'Fixture: close-review test',
        sentiment_summary: 'Neutral',
        active_strategy: 'momentum',
        risk_alerts: [],
        ai_summary: 'Fixture mode',
      },
      lifecycle: {
        lifecycle_state: 'review',
        runtime_state: 'REVIEW',
        session_id: 'fixture-review-session',
        current_pair_symbol: null,
        current_signal_id: null,
        started_at: '2026-07-01T10:00:00Z',
        paused_at: null,
        resume_ready: false,
        can_start: false,
        can_pause: false,
        can_resume: false,
        can_complete: false,
      },
      pending_pair_replacement: null,
    }

    const idleFixture = {
      ...fixture,
      lifecycle: {
        ...fixture.lifecycle,
        lifecycle_state: 'idle',
        runtime_state: 'BACKGROUND_MONITORING',
        session_id: null,
        can_start: true,
      },
    }

    // Stateful mock: overview starts in review, switches to idle after close-review POST
    let isReview = true
    await page.route('**/session/overview', async (route) => {
      await route.fulfill({ json: isReview ? fixture : idleFixture, status: 200 })
    })

    await page.route('**/session/review/close', async (route) => {
      isReview = false
      await route.fulfill({ json: idleFixture, status: 200 })
    })

    // ---------- mount ----------
    page.on('dialog', (dialog) => {
      console.log(`Dialog: ${dialog.message()}`)
      dialog.accept()
    })

    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="session-control"]', { timeout: 15_000 })
    await page.waitForTimeout(2000)

    // ---------- V1: close-review button visible in review state ----------
    const closeBtn = page.locator('.session-lifecycle-console button', { hasText: 'Close review' })
    const closeBtnVisible = await closeBtn.isVisible()
    console.log(`\n=== F12: Close review button visible in review state? ${closeBtnVisible}`)

    // Verify other lifecycle buttons are disabled
    const completeBtn = page.locator('.session-lifecycle-console button', { hasText: 'Complete session' })
    const completeDisabled = await completeBtn.isDisabled()
    console.log(`Complete session disabled in review? ${completeDisabled}`)

    expect(closeBtnVisible).toBe(true)
    expect(completeDisabled).toBe(true)

    // ---------- V2: click close-review → lifecycle transitions to idle ----------
    // (F13 SSE relevance is verified by pytest — 1-line RELEVANT_EVENTS change)
    await closeBtn.click()
    await page.waitForTimeout(1500)

    const lifecycleBadge = page.locator('.session-lifecycle-console [data-status]').first()
    const lifecycleText = await lifecycleBadge.textContent()
    console.log(`\n=== F12 after close-review: lifecycle_state = "${lifecycleText}"`)

    // Check start button is now enabled
    const startBtn = page.locator('.session-command-row button', { hasText: 'Start session' })
    const startEnabled = await startBtn.isEnabled()
    console.log(`Start session enabled after close-review? ${startEnabled}`)

    expect(lifecycleText).toBe('idle')
    expect(startEnabled).toBe(true)

    await page.screenshot({ path: '/tmp/workspace-tour/sc-close-review.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/session/overview')
    await page.unroute('**/session/review/close')
    const realResp = await page.request.get(`${API}/session/overview`)
    const realData = await realResp.json()
    const realLifecycleState = realData.lifecycle.lifecycle_state
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API lifecycle_state: ${realLifecycleState} (fixture was "review")`)
    console.log(`Session id: ${realData.lifecycle.session_id} (fixture had "fixture-review-session")`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)

    expect(realLifecycleState).not.toBe('review')
    // After close-review on a real backend, lifecycle goes to idle
  })
})
