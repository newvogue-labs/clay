from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from clay.api.dependencies import get_override_service
from clay.execution.exceptions import ExecutionConfigError
from clay.execution.service import OverrideService


router = APIRouter(prefix="/workspace/trading/override", tags=["override"])


class OverrideRequestPayload(BaseModel):
    actor: str
    reason: str | None = None


class OverrideConfirmPayload(BaseModel):
    actor: str
    reason: str | None = None


class OverrideRevokePayload(BaseModel):
    actor: str
    reason: str | None = None


class OverrideResponse(BaseModel):
    override_id: str
    status: str | None = None
    expires_at: str | None = None


@router.post("/request", response_model=OverrideResponse)
async def request_override(
    payload: OverrideRequestPayload,
    service: Annotated[OverrideService, Depends(get_override_service)],
) -> OverrideResponse:
    try:
        override_id = await service.request_override(
            actor=payload.actor,
            reason=payload.reason,
        )
    except ExecutionConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OverrideResponse(
        override_id=override_id,
        status=service.status,
    )


@router.post("/confirm", response_model=OverrideResponse)
async def confirm_override(
    payload: OverrideConfirmPayload,
    service: Annotated[OverrideService, Depends(get_override_service)],
) -> OverrideResponse:
    try:
        await service.confirm_override(
            actor=payload.actor,
            reason=payload.reason,
        )
    except ExecutionConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OverrideResponse(
        override_id=service.armed_override_id or "",
        status=service.status,
        expires_at=service.expires_at.isoformat() if service.expires_at else None,
    )


@router.post("/revoke", response_model=OverrideResponse)
async def revoke_override(
    payload: OverrideRevokePayload,
    service: Annotated[OverrideService, Depends(get_override_service)],
) -> OverrideResponse:
    try:
        override_id = await service.revoke_override(
            actor=payload.actor,
            reason=payload.reason or "",
        )
    except ExecutionConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OverrideResponse(
        override_id=override_id,
        status=None,
    )
