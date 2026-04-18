from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_signal_engine_service
from clay.signal_engine.service import SignalEngineService


router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/overview")
async def get_signal_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SignalEngineService, Depends(get_signal_engine_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")
