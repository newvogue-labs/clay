from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_demo_trading_service
from clay.demo_trading.models import DemoResultIngestCommand, DemoTradeLogCommand
from clay.demo_trading.service import DemoTradingService


router = APIRouter(prefix="/demo-trading", tags=["demo-trading"])


@router.get("/overview")
async def get_demo_trading_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[DemoTradingService, Depends(get_demo_trading_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.post("/log-current")
async def log_current_demo_trade(
    command: DemoTradeLogCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[DemoTradingService, Depends(get_demo_trading_service)],
) -> dict[str, object]:
    try:
        snapshot = service.log_current_trade(session, command)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/results/ingest")
async def ingest_demo_result(
    command: DemoResultIngestCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[DemoTradingService, Depends(get_demo_trading_service)],
) -> dict[str, object]:
    try:
        snapshot = service.ingest_result(
            session,
            record_id=command.record_id,
            external_trade_id=command.external_trade_id,
            broker_status=command.broker_status,
            entry_price=command.entry_price,
            exit_price=command.exit_price,
            pnl_pct=command.pnl_pct,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")
