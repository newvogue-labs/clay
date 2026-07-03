export type KellyConfig = {
  lambda_: number
  cap: number
  min_ev: number
  equity_base: number
}

export type CalibrationConfig = {
  min_outcomes_for_recalibration: number
}

export type SessionLimitsConfig = {
  max_drawdown_pct: number
  max_consecutive_losses: number
  cooldown_minutes: number
  drawdown_window_hours: number
  max_concurrent_sessions: number
  max_total_exposure_pct: number
  max_total_exposure_block_pct: number
  per_session_loss_warn_pct: number
}

export type RiskConfig = {
  confidence_warning_threshold: number
  degraded_confidence_penalty: number
  kelly: KellyConfig
  calibration: CalibrationConfig
  session_limits: SessionLimitsConfig
}

export type RuntimeConfig = {
  work_window_start: string
  work_window_end: string
  default_state: string
}

export type ConfigsSnapshot = {
  config_dir: string
  items: {
    risk: RiskConfig
    runtime: RuntimeConfig
  }
  ui_mutable_scopes: string[]
}
