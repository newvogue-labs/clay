from typing import TypedDict

from clay.alpha.service import AlphaReadinessService
from clay.demo_trading.service import DemoTradingService
from clay.reliability.service import ReliabilityService
from clay.runtime.manager import RuntimeManager
from clay.services.registry import ServiceRegistry
from clay.session_control.service import SessionControlService
from clay.session_review.service import SessionReviewService
from clay.validation_lab.service import ValidationLabService


class AlphaBundle(TypedDict):
    service: AlphaReadinessService
    session_control_service: SessionControlService
    demo_trading_service: DemoTradingService
    session_review_service: SessionReviewService
    validation_lab_service: ValidationLabService
    reliability_service: ReliabilityService


class ReliabilityBundle(TypedDict):
    service: ReliabilityService
    runtime_manager: RuntimeManager
    registry: ServiceRegistry
    validation_lab_service: ValidationLabService
