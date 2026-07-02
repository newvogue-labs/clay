import { test, expect } from '@playwright/test'

const SCREEN = '#demo-validation'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('C-recheck: visual distinction of non-match outcomes', () => {
  test('Fixture with mixed outcomes — DOM dump + screenshots + teardown', async ({ page }) => {
    // ---------- fixture ----------
    const fixture = {
      readiness: {
        status: 'ready_for_review',
        operator_message: 'Fixture: mixed outcomes for C-recheck',
        distinct_session_count: 1,
        total_records: 5,
        resolved_record_count: 5,
        profitable_record_count: 3,
        cumulative_pnl_pct: 1.8,
        outcome_counts: { matched: 1, missed: 1, late_matched: 1, mismatched: 1, unresolved: 1 },
        gates: [
          { gate_id: 'g1', label: 'Session count', status: 'pass', detail: '1 session recorded.' },
          { gate_id: 'g2', label: 'Result resolution', status: 'pass', detail: '5 resolved.' },
          { gate_id: 'g3', label: 'Signal alignment', status: 'warn', detail: '1 mismatched.' },
          { gate_id: 'g4', label: 'PnL discipline', status: 'pass', detail: '3 profitable vs 2 losing.' },
        ],
      },
      active_session: {
        lifecycle_state: 'active_session',
        session_id: 'fixture-session',
        current_pair_symbol: 'TESTUSDT',
        current_signal_id: 'sig-test',
        can_log_decision: true,
        blocking_reason: null,
      },
      records: [
        {
          record_id: 1, session_id: 's1', signal_id: 'sig-m', symbol: 'SOLUSDT',
          operator_action: 'entered', operator_notes: null,
          recorded_at: '2026-06-30T10:00:00Z', external_trade_id: null,
          broker_status: 'closed', entry_price: 100, exit_price: 101.2,
          pnl_pct: 1.2, observed_at: '2026-06-30T10:05:00Z',
          outcome_status: 'matched', awaiting_result: false,
          executed_symbol: null,
        },
        {
          record_id: 2, session_id: 's1', signal_id: 'sig-lm', symbol: 'SOLUSDT',
          operator_action: 'entered_late', operator_notes: null,
          recorded_at: '2026-06-30T11:00:00Z', external_trade_id: null,
          broker_status: 'closed', entry_price: 105, exit_price: 104.5,
          pnl_pct: -0.5, observed_at: '2026-06-30T11:05:00Z',
          outcome_status: 'late_matched', awaiting_result: false,
          executed_symbol: null,
        },
        {
          record_id: 3, session_id: 's1', signal_id: 'sig-mm', symbol: 'ETHUSDT',
          operator_action: 'entered', operator_notes: null,
          recorded_at: '2026-06-30T12:00:00Z', external_trade_id: null,
          broker_status: 'closed', entry_price: 200, exit_price: 202.1,
          pnl_pct: 1.05, observed_at: '2026-06-30T12:05:00Z',
          outcome_status: 'mismatched', awaiting_result: false,
          executed_symbol: null,
        },
        {
          record_id: 4, session_id: 's1', signal_id: 'sig-u', symbol: 'BTCUSDT',
          operator_action: 'skipped', operator_notes: null,
          recorded_at: '2026-06-30T13:00:00Z', external_trade_id: null,
          broker_status: null, entry_price: null, exit_price: null,
          pnl_pct: null, observed_at: null,
          outcome_status: 'unresolved', awaiting_result: true,
          executed_symbol: null,
        },
        {
          record_id: 5, session_id: 's1', signal_id: 'sig-ms', symbol: 'SOLUSDT',
          operator_action: 'off_signal', operator_notes: null,
          recorded_at: '2026-06-30T14:00:00Z', external_trade_id: null,
          broker_status: 'closed', entry_price: 110, exit_price: 108.2,
          pnl_pct: -1.6, observed_at: '2026-06-30T14:05:00Z',
          outcome_status: 'missed', awaiting_result: false,
          executed_symbol: null,
        },
      ],
    }

    await page.route('**/demo-trading/overview', async (route) => {
      await route.fulfill({ json: fixture, status: 200 })
    })

    // ---------- mount ----------
    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="demo-validation"]', { timeout: 15_000 })
    await page.waitForTimeout(3000)

    // ---------- OutcomeMix: data-tone dump ----------
    const outcomeMix = page.locator('.demo-outcome-console .demo-outcome-list')
    const oRows = outcomeMix.locator('p')
    const oCount = await oRows.count()
    console.log(`\n=== OUTCOME MIX: ${oCount} rows ===`)
    for (let i = 0; i < oCount; i++) {
      const r = oRows.nth(i)
      const tone = await r.getAttribute('data-tone')
      const text = await r.textContent()
      console.log(`  [${i}] data-tone="${tone}" text="${text?.trim()}"`)
    }

    // ---------- Record rows: StatusBadge + styling dump ----------
    const rows = page.locator('.demo-record-row')
    const rCount = await rows.count()
    console.log(`\n=== RECORD ROWS: ${rCount} ===`)
    for (let i = 0; i < rCount; i++) {
      const row = rows.nth(i)
      const recordId = await row.locator('div').first().locator('strong').first().textContent()

      // StatusBadge (outcome_status) — exact class list
      const statusEl = row.locator('[data-status]')
      const statusVal = await statusEl.getAttribute('data-status')
      const statusClass = await statusEl.getAttribute('class')

      // PnL block
      const pnlDiv = row.locator('div').nth(3)
      const pnlClass = await pnlDiv.getAttribute('class')
      const pnlText = await pnlDiv.locator('strong').textContent()
      const hasTrendingUp = (await pnlDiv.locator('svg').count()) > 0

      // Result
      const resultText = await row.locator('.demo-result-actions').textContent()

      console.log(`\n  --- Record #${i} (${recordId}) ---`)
      console.log(`  outcome_status data-status="${statusVal}"`)
      console.log(`  StatusBadge class="${statusClass}"`)
      console.log(`  PnL div class="${pnlClass}" text="${pnlText}"`)
      console.log(`  Has TrendingUp icon: ${hasTrendingUp}`)
      console.log(`  Result: "${resultText?.trim()}"`)
    }

    // ---------- Screenshot ----------
    await page.screenshot({ path: '/tmp/workspace-tour/dv-c-recheck.png', fullPage: true })

    // ---------- Assertions ----------
    // OutcomeMix: data-tone must differ
    const matchTone = await outcomeMix.locator('p').nth(0).getAttribute('data-tone')
    const lateTone = await outcomeMix.locator('p').nth(2).getAttribute('data-tone')
    const mmTone = await outcomeMix.locator('p').nth(3).getAttribute('data-tone')
    const unTone = await outcomeMix.locator('p').nth(4).getAttribute('data-tone')

    console.log(`\n=== ASSERTIONS ===`)
    console.log(`matched data-tone="${matchTone}"`)
    console.log(`late_matched data-tone="${lateTone}"`)
    console.log(`mismatched data-tone="${mmTone}"`)
    console.log(`unresolved data-tone="${unTone}"`)

    expect(matchTone).toBe('success')
    expect(lateTone).toBe('warning')
    expect(mmTone).toBe('danger')
    expect(unTone).toBe('warning')

    // Record row StatusBadge: AFTER FIX — tone prop forces correct class
    const matchedBadgeClass = await rows.nth(0).locator('[data-status]').getAttribute('class') || ''
    const mmBadgeClass = await rows.nth(2).locator('[data-status]').getAttribute('class') || ''
    const matchedIsSuccess = matchedBadgeClass.includes('clay-success')
    const mmIsDanger = mmBadgeClass.includes('clay-danger')

    console.log(`\nStatusBadge class check (AFTER tone-prop fix):`)
    console.log(`  matched StatusBadge contains clay-success: ${matchedIsSuccess}`)
    console.log(`  mismatched StatusBadge contains clay-danger: ${mmIsDanger}`)
    console.log(`  Classes differ: ${matchedBadgeClass !== mmBadgeClass}`)

    // CRITICAL: mismatched must NOT use fallback gray — must use danger red
    expect(mmIsDanger).toBe(true)
    expect(matchedIsSuccess).toBe(true)
    expect(matchedBadgeClass).not.toBe(mmBadgeClass)

    // PnL: positive -> is-positive (green), negative -> is-negative (red)
    const matchedPnlClass = await rows.nth(0).locator('div').nth(3).getAttribute('class')
    const mmPnlClass = await rows.nth(2).locator('div').nth(3).getAttribute('class')
    console.log(`\nPnL styling:`)
    console.log(`  matched (pnl=+1.2%) class="${matchedPnlClass}"`)
    console.log(`  mismatched (pnl=+1.05%) class="${mmPnlClass}"`)

    // Record row #2 (mismatched) has positive PnL + mismatched badge → check if it LOOKS like success
    const mmRow = rows.nth(2)
    const mmStatusBadgeClass = await mmRow.locator('[data-status]').getAttribute('class')
    const mmPnlDivClass = await mmRow.locator('div').nth(3).getAttribute('class')
    const mmStatus = await mmRow.locator('[data-status]').getAttribute('data-status')

    console.log(`\n=== MISMATCHED ROW (POSITIVE PnL) — CRITICAL CHECK ===`)
    console.log(`  StatusBadge: data-status="${mmStatus}" class="${mmStatusBadgeClass}"`)
    console.log(`  PnL div: class="${mmPnlDivClass}"`)

    await page.screenshot({ path: '/tmp/workspace-tour/dv-c-mismatched-positive.png', fullPage: true })

    console.log(`\nScreenshots: /tmp/workspace-tour/dv-c-recheck.png, /tmp/workspace-tour/dv-c-mismatched-positive.png`)

    // ---------- TEARDOWN: фикстура изолирована, реальные данные не тронуты ----------
    // Чистим route-перехват и сверяемся напрямую с API (не через DOM — cache может держать фикстуру)
    await page.unroute('**/demo-trading/overview')
    const realResp = await page.request.get(`${API}/demo-trading/overview`)
    const realData = await realResp.json()
    const realTotalRecords = realData.readiness.total_records
    const realSessions = realData.readiness.distinct_session_count
    const realSessionId = realData.active_session.session_id
    const realPair = realData.active_session.current_pair_symbol

    console.log(`\n=== TEARDOWN (API-direct) ===`)
    console.log(`API total_records: ${realTotalRecords} (fixture had 5)`)
    console.log(`API distinct_sessions: ${realSessions}`)
    console.log(`Session id: ${realSessionId} (fixture had "fixture-session")`)
    console.log(`Current pair: ${realPair} (fixture had TESTUSDT)`)
    console.log(`\nVERDICT: Backend state unchanged. Fixture was 100% in-memory via page.route().`)

    expect(realSessionId).not.toBe('fixture-session')
    expect(realPair).not.toBe('TESTUSDT')
    expect(realTotalRecords).toBe(21)
    expect(realSessions).toBe(21)
  })
})
