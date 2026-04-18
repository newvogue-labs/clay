import { useState } from 'react'

import { AIControlPage } from './features/ai-control/ai-control-page'
import { ControlCenterPage } from './features/control-center/control-center-page'
import { TradingWorkspacePage } from './features/workspace/trading-workspace-page'

export function App() {
  const [screen, setScreen] = useState<'workspace' | 'control-center' | 'ai-control'>('workspace')

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
      </nav>
      {screen === 'workspace' ? <TradingWorkspacePage /> : null}
      {screen === 'control-center' ? <ControlCenterPage /> : null}
      {screen === 'ai-control' ? <AIControlPage /> : null}
    </main>
  )
}

export default App
