from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_session_review_service
from clay.session_review.models import FeedbackCreateCommand
from clay.session_review.service import SessionReviewService


router = APIRouter(prefix="/session-review", tags=["session-review"])


@router.get("/overview")
async def get_session_review_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionReviewService, Depends(get_session_review_service)],
    pair: Annotated[str | None, Query()] = None,
    strategy: Annotated[str | None, Query()] = None,
    model_version: Annotated[str | None, Query()] = None,
    confidence_band: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    return service.build_snapshot(
        session,
        pair=pair,
        strategy=strategy,
        model_version=model_version,
        confidence_band=confidence_band,
    ).model_dump(mode="json")


@router.post("/feedback")
async def capture_session_feedback(
    command: FeedbackCreateCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[SessionReviewService, Depends(get_session_review_service)],
) -> dict[str, object]:
    try:
        snapshot = service.capture_feedback(session, command)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return snapshot.model_dump(mode="json")
