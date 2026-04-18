from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clay.ai_control.models import AssignmentApplyCommand, AssignmentReviewCommand
from clay.ai_control.service import AIControlService
from clay.api.dependencies import get_ai_control_service, get_db_session


router = APIRouter(prefix="/ai-control", tags=["ai-control"])


@router.get("/overview")
async def get_ai_control_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AIControlService, Depends(get_ai_control_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.post("/assignments/review")
async def review_ai_assignment(
    command: AssignmentReviewCommand,
    service: Annotated[AIControlService, Depends(get_ai_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.review_assignment(command.role_id, command.model_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/assignments/apply")
async def apply_ai_assignment(
    command: AssignmentApplyCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[AIControlService, Depends(get_ai_control_service)],
) -> dict[str, object]:
    del session
    try:
        snapshot = service.apply_assignment(command.review_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return snapshot.model_dump(mode="json")
