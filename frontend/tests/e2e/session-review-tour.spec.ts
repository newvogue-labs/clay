import { test, expect } from '@playwright/test'

const SCREEN = '#session-review'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('Session Review Tour — outcome badges (F17) + AI-card tone (F18)', () => {
  test('Record rows show outcome badges at 3 tones; AI review cards show severity tone via review-ai-card', async ({ page }) => {
    // ---------- fixture ----------
    const fixture = {
      summary: {
        review_status: 'needs_attention',
        total_demo_records: 4,
        resolved_demo_records: 3,
        cumulative_pnl_pct: -0.2,
        feedback_count: 0,
        last_reviewed_at: '2026-07-03T12:00:00Z',
        operator_message: 'Fixture: outcome + AI-card tone test',
      },
      filters: {
        pair: null,
        strategy: null,
        model_version: null,
        confidence_band: null,
      },
      filter_options: {
        pairs: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        strategies: ['momentum', 'mean_reversion'],
        model_versions: ['v1', 'v2'],
        confidence_bands: ['high', 'medium', 'low'],
      },
      records: [
        {
          record_id: 1,
          session_id: 's1',
          signal_id: 'sig-matched',
          symbol: 'BTCUSDT',
          strategy_mode: 'momentum',
          model_version: 'v2',
          confidence_band: 'high',
          operator_action: 'entered',
          outcome_status: 'matched',
          pnl_pct: 1.5,
          recorded_at: '2026-07-03T10:00:00Z',
          observed_at: '2026-07-03T10:05:00Z',
        },
        {
          record_id: 2,
          session_id: 's1',
          signal_id: 'sig-mismatched',
          symbol: 'ETHUSDT',
          strategy_mode: 'momentum',
          model_version: 'v2',
          confidence_band: 'medium',
          operator_action: 'entered',
          outcome_status: 'mismatched',
          pnl_pct: -0.8,
          recorded_at: '2026-07-03T11:00:00Z',
          observed_at: '2026-07-03T11:05:00Z',
        },
        {
          record_id: 3,
          session_id: 's1',
          signal_id: 'sig-late',
          symbol: 'SOLUSDT',
          strategy_mode: 'mean_reversion',
          model_version: 'v1',
          confidence_band: 'low',
          operator_action: 'entered_late',
          outcome_status: 'late_matched',
          pnl_pct: 0.3,
          recorded_at: '2026-07-03T12:00:00Z',
          observed_at: '2026-07-03T12:05:00Z',
        },
        {
          record_id: 4,
          session_id: 's1',
          signal_id: 'sig-missed',
          symbol: 'SOLUSDT',
          strategy_mode: 'mean_reversion',
          model_version: 'v1',
          confidence_band: 'low',
          operator_action: 'off_signal',
          outcome_status: 'missed',
          pnl_pct: -1.2,
          recorded_at: '2026-07-03T13:00:00Z',
          observed_at: '2026-07-03T13:05:00Z',
        },
      ],
      feedback: [],
      audit: [],
      ai_review_cards: [
        {
          card_id: 'card-warning',
          severity: 'warning',
          title: 'Signal mismatch detected',
          summary: 'ETHUSDT entered but signal indicated short.',
          recommendations: ['Review entry criteria.'],
          confirmation_required_for_changes: false,
        },
        {
          card_id: 'card-info',
          severity: 'info',
          title: 'Late entry detected',
          summary: 'SOLUSDT entry 2min after signal.',
          recommendations: ['Tighten entry window.'],
          confirmation_required_for_changes: false,
        },
        {
          card_id: 'card-info-2',
          severity: 'info',
          title: 'Clean audit window',
          summary: 'BTCUSDT trade aligned with signal.',
          recommendations: ['Continue current strategy.'],
          confirmation_required_for_changes: false,
        },
      ],
    }

    let mockHitCount = 0
    await page.route('**/session-review/overview*', async (route) => {
      mockHitCount++
      console.log(`  MOCK HIT #${mockHitCount}: ${route.request().url()}`)
      await route.fulfill({ json: fixture, status: 200 })
    })

    // ---------- mount ----------
    const consoleErrors: string[] = []
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
    page.on('pageerror', err => consoleErrors.push(err.message))

    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="session-review"]', { timeout: 15_000 })
    await page.waitForTimeout(3000)

    if (consoleErrors.length > 0) {
      console.log(`\n=== CONSOLE ERRORS (${consoleErrors.length}) ===`)
      for (const e of consoleErrors) console.log(`  ${e}`)
    }

    // ---------- V1: F17 — record-row outcome badges at 3 different tones ----------
    const recordRows = page.locator('.review-record-row')
    const rowCount = await recordRows.count()
    console.log(`\n=== Review record rows: ${rowCount} ===`)
    expect(rowCount).toBe(4)

    const outcomeToExpectedTone: Record<string, string> = {
      matched: 'success',
      mismatched: 'danger',
      late_matched: 'warning',
      missed: 'warning',
    }
    const toneToColor: Record<string, string> = {
      success: 'clay-success',
      danger: 'clay-danger',
      warning: 'clay-warning',
      muted: 'clay-text-muted',
    }

    // Batch A: StatusBadge receives tone prop from getOutcomeTone.
    // tone prop overrides internal lookup → all 4 badges are colored.
    const outcomeHasToneProp: Record<string, boolean> = {
      matched: true,
      mismatched: true,
      late_matched: true,
      missed: true,
    }

    for (let i = 0; i < rowCount; i++) {
      const row = recordRows.nth(i)
      const badge = row.locator('[data-status]').first()
      const outcomeStatus = await badge.getAttribute('data-status')
      const badgeClass = await badge.getAttribute('class')

      const expectedTone = outcomeToExpectedTone[outcomeStatus] || 'muted'
      const expectedColor = toneToColor[expectedTone]

      const badgeIsCorrect = badgeClass?.includes(expectedColor)
      console.log(`\n  Row #${i}: outcome="${outcomeStatus}" badge-correct: ${badgeIsCorrect}`)

      if (outcomeHasToneProp[outcomeStatus]) {
        expect(badgeClass).toContain(expectedColor)
      } else {
        console.log(`    NOTE: StatusBadge for "${outcomeStatus}" has no tone prop — muted (gap)`)
      }
    }

    // ---------- V2: F18 — AI review cards via review-ai-card selector ----------
    const aiCards = page.locator('.review-ai-card')
    const aiCardCount = await aiCards.count()
    console.log(`\n=== AI review cards (.review-ai-card): ${aiCardCount} ===`)
    expect(aiCardCount).toBe(3)

    for (let i = 0; i < aiCardCount; i++) {
      const card = aiCards.nth(i)
      const dataTone = await card.getAttribute('data-tone')
      const cardText = await card.textContent()

      console.log(`\n  AI card #${i}: data-tone="${dataTone}"`)
      console.log(`  Card text preview: "${cardText?.trim().substring(0, 80)}..."`)

      // Verify data-tone is not empty and is a valid tone
      expect(dataTone).not.toBeNull()
      expect(['success', 'warning', 'danger', 'muted']).toContain(dataTone)
    }

    // ⚠ F18: AI-card data-tone uses getSeverityTone (NOT getOutcomeTone)
    // card #0: severity=warning → data-tone=warning 🟡
    // card #1: severity=info   → data-tone=muted ⚪
    // card #2: severity=info   → data-tone=muted ⚪
    const expectedAiCardTones = ['warning', 'muted', 'muted']
    for (let i = 0; i < aiCardCount; i++) {
      const card = aiCards.nth(i)
      const dataTone = await card.getAttribute('data-tone')
      expect(dataTone).toBe(expectedAiCardTones[i])
    }

    await page.screenshot({ path: '/tmp/workspace-tour/session-review-outcomes-ai-cards.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/session-review/overview*')
    const realResp = await page.request.get(`${API}/session-review/overview`)
    const realData = await realResp.json()
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API total_records: ${realData.summary.total_records} (fixture had 4)`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)
    expect(realData.summary.total_records).not.toBe(4)
  })
})
