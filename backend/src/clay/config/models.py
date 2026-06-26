from pydantic import BaseModel, ConfigDict, Field

from clay.runtime.states import RuntimeState


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_window_start: str = "09:00"
    work_window_end: str = "22:00"
    default_state: RuntimeState = RuntimeState.BACKGROUND_MONITORING


class KellyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lambda_: float = Field(default=0.25, gt=0.0, le=1.0, alias="lambda")
    cap: float = Field(default=0.02, gt=0.0, le=1.0)
    min_ev: float = Field(default=0.15, ge=0.0)
    equity_base: float = Field(default=1.0, gt=0.0)


class CalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_outcomes_for_recalibration: int = Field(default=30, ge=5)


class SessionLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_drawdown_pct: float = Field(default=15.0, gt=0.0, le=100.0)
    max_consecutive_losses: int = Field(default=3, ge=1)
    cooldown_minutes: int = Field(default=60, ge=0)
    drawdown_window_hours: int = Field(default=24, ge=1)
    max_concurrent_sessions: int = Field(default=1, ge=1)
    max_total_exposure_pct: float = Field(default=4.0, gt=0.0, le=100.0)
    per_session_loss_warn_pct: float = Field(default=8.0, gt=0.0, le=100.0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_warning_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    degraded_confidence_penalty: float = Field(default=0.2, ge=0.0, le=1.0)
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    session_limits: SessionLimitsConfig = Field(default_factory=SessionLimitsConfig)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "dry_run"
    exchange_id: str = "binance_spot"
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = False
    recv_window: int = 5000
    allow_live_override: bool = False
    override_state: str | None = None
