from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clay.alpha.service import AlphaReadinessService
from clay.api.dependencies import get_alpha_readiness_service, get_db_session

router = APIRouter(prefix="/alpha", tags=["alpha"])


@router.get("/overview")
async def get_alpha_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AlphaReadinessService, Depends(get_alpha_readiness_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")
