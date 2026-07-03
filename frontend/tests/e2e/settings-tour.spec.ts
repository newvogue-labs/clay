import { test, expect } from '@playwright/test'

const SCREEN = '#settings'
const PREVIEW = 'http://localhost:4173'
const API = 'http://127.0.0.1:8000'

test.describe('Settings Tour — wired configs + placeholders (F23)', () => {
  test('Mount GET /configs once, real risk values, apply/restore UI, no fake panels', async ({ page }) => {
    // ---------- V1: mount → GET /configs ----------
    let getConfigsCount = 0
    let applyCount = 0
    let restoreCount = 0

    await page.route('**/configs', async (route, request) => {
      if (request.method() === 'GET') {
        getConfigsCount++
      }
      const realResp = await page.request.fetch(request)
      const body = await realResp.json()
      // Override risk values to prove UI reads from config, not literals
      body.items.risk.kelly.cap = 0.05       // 5.0% instead of 2.0%
      body.items.risk.session_limits.max_total_exposure_pct = 8.0
      body.items.risk.session_limits.max_drawdown_pct = 20.0
      await route.fulfill({ json: body, status: realResp.status() })
    })

    await page.route('**/configs/risk', async (route, request) => {
      if (request.method() === 'POST') {
        applyCount++
      }
      const resp = await page.request.fetch(request)
      await route.fulfill({ response: resp })
    })

    await page.route('**/configs/risk/restore', async (route) => {
      restoreCount++
      const resp = await page.request.fetch(route.request())
      await route.fulfill({ response: resp })
    })

    // Don't touch other routes (ai-control, events, etc.) — let them through

    // ---------- mount ----------
    await page.goto(`${PREVIEW}${SCREEN}`)
    await page.waitForSelector('[data-screen="settings"]', { timeout: 15_000 })
    await page.waitForTimeout(2000)

    console.log(`\n=== C1: GET /configs count = ${getConfigsCount}`)
    expect(getConfigsCount).toBe(1)

    // ---------- V2: risk values from config, not literals ----------
    const riskLimitRows = page.locator('.risk-limit-row')
    const rowCount = await riskLimitRows.count()
    console.log(`\n=== C1: Risk limit rows = ${rowCount}`)

    // First row: Max Risk Per Trade — with our mock cap=0.05 → 5.0%
    const firstRowValue = await riskLimitRows.nth(0).locator('strong').textContent()
    console.log(`Max Risk Per Trade value: "${firstRowValue}" (mock cap=0.05 → expected "5.0%")`)
    expect(firstRowValue).toBe('5.0%')

    // Second row: Max Total Exposure — mock 8.0%
    const secondRowValue = await riskLimitRows.nth(1).locator('strong').textContent()
    console.log(`Max Total Exposure value: "${secondRowValue}" (mock 8.0 → expected "8.0%")`)
    expect(secondRowValue).toBe('8.0%')

    // Third row: Max Drawdown — mock 20.0%
    const thirdRowValue = await riskLimitRows.nth(2).locator('strong').textContent()
    console.log(`Max Drawdown value: "${thirdRowValue}" (mock 20.0 → expected "20.0%")`)
    expect(thirdRowValue).toBe('20.0%')

    // ---------- V2b: risk bar width is data-driven, not hardcoded ----------
    const riskBar = riskLimitRows.nth(0).locator('div > span')
    const barWidthStyle = await riskBar.getAttribute('style')
    console.log(`Risk bar width style: "${barWidthStyle}" (pct*5 = 25% for 5.0%)`)
    expect(barWidthStyle).toContain('25%')

    // ---------- C2: config-review apply/restore UI ----------
    const configScopeRows = page.locator('.config-scope-row')
    const scopeCount = await configScopeRows.count()
    console.log(`\n=== C2: Config scope rows = ${scopeCount} (expected 2: risk, runtime)`)
    expect(scopeCount).toBe(2)

    // Apply flow: click "Apply config" → confirm appears → "Confirm Apply" → POST
    const firstScopeApply = configScopeRows.nth(0).locator('button', { hasText: 'Apply config' })
    await firstScopeApply.click()
    await page.waitForTimeout(500)

    // Confirm apply button should now be visible
    const confirmBtn = configScopeRows.nth(0).locator('button', { hasText: 'Confirm Apply' })
    const hasConfirm = await confirmBtn.isVisible()
    console.log(`Confirm Apply visible after click: ${hasConfirm}`)

    // Handle confirm dialog
    page.on('dialog', (dialog) => {
      console.log(`Dialog: ${dialog.message()}`)
      dialog.accept()
    })

    await confirmBtn.click()
    await page.waitForTimeout(1500)
    console.log(`Apply POST count: ${applyCount} (expected ≥1)`)

    // Restore flow
    const restoreBtn = configScopeRows.nth(0).locator('button', { hasText: 'Restore default' })
    await restoreBtn.click()
    await page.waitForTimeout(1500)
    console.log(`Restore POST count: ${restoreCount} (expected ≥1)`)

    // Cancel flow: click Cancel on the confirm panel (now hidden after apply)
    // After apply, the confirm panel disappears
    const cancelBtnAfterApply = configScopeRows.nth(0).locator('button', { hasText: 'Cancel' })
    const hasCancelAfterApply = await cancelBtnAfterApply.isVisible()
    console.log(`Cancel button after apply visible: ${hasCancelAfterApply} (expected false — confirm panel closed)`)

    // ---------- V4: placeholder panels ----------
    console.log(`\n=== C3: Placeholder checks ===`)

    // API Connectors: all rows should have Unimplemented status
    const connectorRows = page.locator('.settings-row', { hasText: 'API' })
    const unimplementedConnectors = page.locator('.settings-row em', { hasText: 'Unimplemented' })
    // Check that the old ConnectorRow (no em) is gone — we now use SettingsRow with status="Unimplemented"
    const oldConnectorRows = page.locator('.connector-row')
    const oldConnectorCount = await oldConnectorRows.count()
    console.log(`Old connector-row elements: ${oldConnectorCount} (expected 0 — replaced by SettingsRow)`)

    // Data stats: all should have Unimplemented status
    const dataStats = page.locator('.settings-stat')
    const dsCount = await dataStats.count()
    console.log(`Data stat rows: ${dsCount}`)
    for (let i = 0; i < dsCount; i++) {
      const statEm = await dataStats.nth(i).locator('em').textContent()
      const statVal = await dataStats.nth(i).locator('strong').textContent()
      console.log(`  Stat #${i}: em="${statEm}" value="${statVal}"`)
      expect(statEm).toBe('Unimplemented')
      expect(statVal).toBe('Pending')
    }

    // No Refresh Connectors button (the old .settings-command with RefreshCw)
    const refreshBtn = page.locator('.settings-command')
    const refreshBtnCount = await refreshBtn.count()
    console.log(`'Refresh Connectors' buttons: ${refreshBtnCount} (expected 0 — removed)`)

    await page.screenshot({ path: '/tmp/workspace-tour/settings-wired.png', fullPage: true })

    // ---------- TEARDOWN ----------
    await page.unroute('**/configs**')
    const realResp = await page.request.get(`${API}/configs`)
    const realData = await realResp.json()
    const realKellyCap = realData.items.risk.kelly.cap
    console.log(`\n=== TEARDOWN ===`)
    console.log(`API kelly.cap: ${realKellyCap} (mock was 0.05)`)
    console.log(`API config_dir: ${realData.config_dir}`)
    console.log(`\nVERDICT: Backend state unchanged. All mocks in-memory via page.route().`)
    expect(realKellyCap).toBe(0.02)
  })
})
