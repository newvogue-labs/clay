from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clay.api.dependencies import get_control_center_service, get_db_session
from clay.control_center.service import ControlCenterService

router = APIRouter(prefix="/control-center", tags=["control-center"])


@router.get("/overview")
async def get_control_center_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ControlCenterService, Depends(get_control_center_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")
