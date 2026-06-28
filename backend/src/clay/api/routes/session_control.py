from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_session_control_service
from clay.session_control.models import (
    PairReplacementApplyCommand,
    PairReplacementReviewCommand,
)
from clay.session_control.service import SessionControlService


router = APIRouter(prefix="/session", tags=["session"])


@router.get("/overview")
async def get_session_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.post("/start")
async def start_session(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.start_session(session)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/pause")
async def pause_session(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.pause_session(session)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/resume")
async def resume_session(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.resume_session(session)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/complete")
async def complete_session(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.complete_session(session)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/review/close")
async def close_review(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.close_review(session)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")


@router.post("/replacement/review")
async def review_pair_replacement(
    command: PairReplacementReviewCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        review = service.review_pair_replacement(
            session, proposed_symbol=command.proposed_symbol
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return review.model_dump(mode="json")


@router.post("/replacement/apply")
async def apply_pair_replacement(
    command: PairReplacementApplyCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionControlService, Depends(get_session_control_service)],
) -> dict[str, object]:
    try:
        snapshot = service.apply_pair_replacement(session, command.review_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")
