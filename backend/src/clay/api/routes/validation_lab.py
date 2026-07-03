from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_validation_lab_service
from clay.validation_lab.models import (
    ActivationApplyCommand,
    ActivationReviewCommand,
    ValidationRunCommand,
)
from clay.validation_lab.service import ValidationLabService


router = APIRouter(prefix="/validation-lab", tags=["validation-lab"])


@router.get("/overview")
async def get_validation_lab_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ValidationLabService, Depends(get_validation_lab_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.post("/runs")
async def run_validation_lab(
    command: ValidationRunCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ValidationLabService, Depends(get_validation_lab_service)],
) -> dict[str, object]:
    return service.run_validation(session, command).model_dump(mode="json")


@router.post("/activation/review")
async def review_activation(
    command: ActivationReviewCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ValidationLabService, Depends(get_validation_lab_service)],
) -> dict[str, object]:
    return service.review_activation(
        session,
        target_type=command.target_type,
        target_id=command.target_id,
        proposed_value=command.proposed_value,
    ).model_dump(mode="json")


@router.post("/activation/apply")
async def apply_activation(
    command: ActivationApplyCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ValidationLabService, Depends(get_validation_lab_service)],
) -> dict[str, object]:
    return service.apply_activation(session, command.review_id).model_dump(mode="json")


@router.post("/activation/review/{review_id}/discard")
async def discard_activation_review(
    review_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[ValidationLabService, Depends(get_validation_lab_service)],
) -> dict[str, object]:
    try:
        snapshot = service.discard_activation_review(session, review_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")
