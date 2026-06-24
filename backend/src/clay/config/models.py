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


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_warning_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    degraded_confidence_penalty: float = Field(default=0.2, ge=0.0, le=1.0)
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
