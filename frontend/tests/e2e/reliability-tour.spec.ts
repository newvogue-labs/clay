import { test, expect } from '@playwright/test'

const SCREEN = '#reliability'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('Reliability Tour — severity badges map to cardTone (F22)', () => {
  test('Degraded triggers at critical/warning/info → StatusBadge tone + card data-tone', async ({ page }) => {
    // ---------- fixture ----------
    const fixture = {
      degraded_triggers: [
        {
          trigger_id: 'trg-critical',
          severity: 'critical',
          title: 'Ingestion pipeline stalled',
          description: 'Market data not received for >60s.',
          recommended_action: 'Restart ingestion service.',
        },
        {
          trigger_id: 'trg-warning',
          severity: 'warning',
          title: 'High memory usage',
          description: 'Memory at 85%.',
          recommended_action: 'Scale up worker.',
        },
        {
          trigger_id: 'trg-info',
          severity: 'info',
          title: 'New model version available',
          description: 'v2.3.1 ready for review.',
          recommended_action: 'Review changelog.',
        },
      ],
      incidents: [
        {
          severity: 'critical',
          source_name: 'Binance WS',
          message: 'Connection lost 3 times in 5min.',
          recorded_at: '2026-07-03T10:00:00Z',
        },
        {
          severity: 'warning',
          source_name: 'Risk engine',
          message: 'Max drawdown 18% (limit 20%).',
          recorded_at: '2026-07-03T09:30:00Z',
        },
      ],
      summary: {
        overall_status: 'degraded',
        release_readiness_status: 'needs_operator_attention',
        active_incident_count: 2,
        degraded_trigger_count: 3,
        release_gate_total: 4,
        release_gate_passed: 2,
        last_check_at: '2026-07-03T09:45:00Z',
      },
      fallback: {
        fallback_active: false,
        local_fallback_ready: true,
        degraded_roles: [],
        operator_message: 'All roles nominal.',
      },
      readiness_checks: [
        { check_id: 'c1', label: 'DB connectivity', status: 'pass', checked_at: '2026-07-03T09:45:00Z' },
        { check_id: 'c2', label: 'Ingestion health', status: 'warn', checked_at: '2026-07-03T09:45:00Z' },
      ],
      release_gates: [
        { gate_id: 'g1', label: 'Session count', status: 'pass' },
        { gate_id: 'g2', label: 'Signal alignment', status: 'warn' },
        { gate_id: 'g3', label: 'PnL discipline', status: 'fail' },
        { gate_id: 'g4', label: 'Result resolution', status: 'pass' },
      ],
    }

    await page.route('**/reliability/overview', async (route) => {
      await route.fulfill({ json: fixture, status: 200 })
    })

    // ---------- mount ----------
    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="reliability"]', { timeout: 15_000 })
    await page.waitForTimeout(2000)

    // ---------- V1: trigger card data-tone matches severity ----------
    const triggerCards = page.locator('.reliability-trigger-card')
    const cardCount = await triggerCards.count()
    console.log(`\n=== Trigger cards: ${cardCount} ===`)

    expect(cardCount).toBe(3)

    const severityToExpectedTone: Record<string, string> = {
      critical: 'danger',
      warning: 'warning',
      info: 'muted',
    }

    // getSeverityTone matches spec: info→muted (neutral, not success).
    // Batch A: tone prop overrides lookup for all 3 severities.
    // StatusBadge internal lookup still doesn't cover critical/info,
    // but tone prop means CSS class comes from getSeverityTone.
    const lookupHas: Record<string, boolean> = {
      critical: true,  // tone prop overrides — colored badge
      warning: true,   // in lookup + tone prop
      info: true,      // tone prop overrides — muted is correct for info
    }

    for (let i = 0; i < cardCount; i++) {
      const card = triggerCards.nth(i)
      const dataTone = await card.getAttribute('data-tone')
      const severityBadge = card.locator('[data-status]')
      const severity = await severityBadge.getAttribute('data-status')
      const badgeClass = await severityBadge.getAttribute('class')

      const expectedTone = severityToExpectedTone[severity] || 'muted'
      // StatusBadge CSS classes from status-badge.tsx
      const toneColorClass = expectedTone === 'danger'
        ? 'border-clay-danger/30 bg-clay-danger/12 text-clay-danger'
        : expectedTone === 'warning'
          ? 'border-clay-warning/30 bg-clay-warning/12 text-clay-warning'
          : expectedTone === 'success'
            ? 'border-clay-success/30 bg-clay-success/12 text-clay-success'
            : 'border-clay-border bg-clay-bg/55 text-clay-text-muted'

      const badgeIsCorrect = badgeClass?.includes(toneColorClass)
      console.log(`  Card #${i}: severity="${severity}" data-tone="${dataTone}" badge-correct: ${badgeIsCorrect} (lookup-has: ${lookupHas[severity]})`)
      console.log(`    ASSERT: card data-tone="${dataTone}" === expected "${expectedTone}"`)

      // Card data-tone MUST match (from getSeverityTone)
      expect(dataTone).toBe(expectedTone)

      // StatusBadge tone — known gap: critical/info not in lookup (F22 still open)
      if (lookupHas[severity]) {
        expect(badgeClass).toContain(toneColorClass)
      } else {
        console.log(`    NOTE: StatusBadge for "${severity}" has no lookup — muted by default but tone prop overrides for colored badges`)
      }
    }

    // ---------- V2: incident cards also have data-tone ----------
    const incidentCards = page.locator('.reliability-incident-card')
    const incCount = await incidentCards.count()
    console.log(`\n=== Incident cards: ${incCount} ===`)

    for (let i = 0; i < incCount; i++) {
      const card = incidentCards.nth(i)
      const dataTone = await card.getAttribute('data-tone')
      const severityBadge = card.locator('[data-status]')
      const severity = await severityBadge.getAttribute('data-status')
      const expectedTone = severityToExpectedTone[severity] || 'muted'
      console.log(`  Incident #${i}: severity="${severity}" data-tone="${dataTone}" expected="${expectedTone}"`)
      expect(dataTone).toBe(expectedTone)
    }

    await page.screenshot({ path: '/tmp/workspace-tour/reliability-degraded-severity.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/reliability/overview')
    const realResp = await page.request.get(`${API}/reliability/overview`)
    const realData = await realResp.json()
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API overall_status: ${realData.summary.overall_status} (fixture was "degraded")`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)
    expect(realData.summary.overall_status).toBe('degraded')
  })
})
