import { useState } from 'react'

import { AIControlPage } from './features/ai-control/ai-control-page'
import { ControlCenterPage } from './features/control-center/control-center-page'
import { DemoValidationPage } from './features/demo-trading/demo-validation-page'
import { KnowledgePage } from './features/knowledge/knowledge-page'
import { ReliabilityPage } from './features/reliability/reliability-page'
import { SessionControlPage } from './features/session-control/session-control-page'
import { SessionReviewPage } from './features/session-review/session-review-page'
import { ValidationLabPage } from './features/validation-lab/validation-lab-page'
import { TradingWorkspacePage } from './features/workspace/trading-workspace-page'

export function App() {
  const [screen, setScreen] = useState<
    | 'workspace'
    | 'control-center'
    | 'ai-control'
    | 'session-control'
    | 'demo-validation'
    | 'session-review'
    | 'knowledge'
    | 'validation-lab'
    | 'reliability'
  >('workspace')

  return (
    <main>
      <h1>Clay</h1>
      <p>Analyst-first trading workspace with a neighboring control center for runtime operations.</p>
      <nav aria-label="screen-switcher">
        <button
          aria-pressed={screen === 'workspace'}
          onClick={() => {
            setScreen('workspace')
          }}
          type="button"
        >
          Trading Workspace
        </button>
        <button
          aria-pressed={screen === 'control-center'}
          onClick={() => {
            setScreen('control-center')
          }}
          type="button"
        >
          Control Center
        </button>
        <button
          aria-pressed={screen === 'ai-control'}
          onClick={() => {
            setScreen('ai-control')
          }}
          type="button"
        >
          AI Control
        </button>
        <button
          aria-pressed={screen === 'session-control'}
          onClick={() => {
            setScreen('session-control')
          }}
          type="button"
        >
          Session Control
        </button>
        <button
          aria-pressed={screen === 'demo-validation'}
          onClick={() => {
            setScreen('demo-validation')
          }}
          type="button"
        >
          Demo Validation
        </button>
        <button
          aria-pressed={screen === 'session-review'}
          onClick={() => {
            setScreen('session-review')
          }}
          type="button"
        >
          Session Review
        </button>
        <button
          aria-pressed={screen === 'knowledge'}
          onClick={() => {
            setScreen('knowledge')
          }}
          type="button"
        >
          Knowledge Base
        </button>
        <button
          aria-pressed={screen === 'validation-lab'}
          onClick={() => {
            setScreen('validation-lab')
          }}
          type="button"
        >
          Validation Lab
        </button>
        <button
          aria-pressed={screen === 'reliability'}
          onClick={() => {
            setScreen('reliability')
          }}
          type="button"
        >
          Reliability Center
        </button>
      </nav>
      {screen === 'workspace' ? <TradingWorkspacePage /> : null}
      {screen === 'control-center' ? <ControlCenterPage /> : null}
      {screen === 'ai-control' ? <AIControlPage /> : null}
      {screen === 'session-control' ? <SessionControlPage /> : null}
      {screen === 'demo-validation' ? <DemoValidationPage /> : null}
      {screen === 'session-review' ? <SessionReviewPage /> : null}
      {screen === 'knowledge' ? <KnowledgePage /> : null}
      {screen === 'validation-lab' ? <ValidationLabPage /> : null}
      {screen === 'reliability' ? <ReliabilityPage /> : null}
    </main>
  )
}

export default App
