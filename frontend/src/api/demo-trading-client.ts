import type { DemoTradingSnapshot } from '../types/demo-trading'

const API_BASE_URL =
  import.meta.env.VITE_CLAY_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

async function postJson<T>(path: string, body: object): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

export function getDemoTradingOverview(): Promise<DemoTradingSnapshot> {
  return getJson<DemoTradingSnapshot>('/demo-trading/overview')
}

export function logCurrentDemoTrade(
  operatorAction: 'entered' | 'skipped' | 'off_signal' | 'entered_late',
): Promise<DemoTradingSnapshot> {
  return postJson<DemoTradingSnapshot>('/demo-trading/log-current', {
    operator_action: operatorAction,
  })
}

export function ingestDemoResult(
  recordId: number,
  pnlPct: number,
  {
    entryPrice = 100,
    exitPrice = 100 + pnlPct,
    brokerStatus = 'closed',
    externalTradeId = null,
  }: {
    entryPrice?: number
    exitPrice?: number
    brokerStatus?: string
    externalTradeId?: string | null
  } = {},
): Promise<DemoTradingSnapshot> {
  return postJson<DemoTradingSnapshot>('/demo-trading/results/ingest', {
    record_id: recordId,
    external_trade_id: externalTradeId,
    broker_status: brokerStatus,
    entry_price: entryPrice,
    exit_price: exitPrice,
    pnl_pct: pnlPct,
  })
}

export function getDemoTradingStreamUrl(): string {
  return `${API_BASE_URL}/demo-trading/stream`
}
