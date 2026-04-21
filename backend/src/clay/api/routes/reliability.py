from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_reliability_service
from clay.reliability.service import ReliabilityService


router = APIRouter(prefix="/reliability", tags=["reliability"])


@router.get("/overview")
async def get_reliability_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReliabilityService, Depends(get_reliability_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.post("/recheck")
async def recheck_reliability(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ReliabilityService, Depends(get_reliability_service)],
) -> dict[str, object]:
    return service.recheck(session).model_dump(mode="json")
