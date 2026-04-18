from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_workspace_service
from clay.bootstrap import audit_writer, event_bus
from clay.workspace.models import FocusCommand
from clay.workspace.service import WorkspaceService


router = APIRouter(prefix="/workspace/trading", tags=["workspace"])


@router.get("")
async def get_trading_workspace_snapshot(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict[str, object]:
    return service.build_snapshot(session).model_dump(mode="json")


@router.get("/focus")
async def get_trading_focus(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict[str, object]:
    return service.build_focus_snapshot(session).model_dump(mode="json")


@router.post("/focus")
async def set_focus_pair(
    payload: FocusCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[WorkspaceService, Depends(get_workspace_service)],
) -> dict[str, object]:
    service.set_focus(
        symbol=payload.symbol,
        focus_source=payload.focus_source,
        signal_id=payload.signal_id,
    )
    snapshot = service.build_focus_snapshot(session).model_dump(mode="json")
    audit_writer.write(
        "workspace.focus.changed",
        {
            "symbol": payload.symbol,
            "focus_source": payload.focus_source,
            "signal_id": payload.signal_id,
        },
    )
    event_bus.publish(
        "workspace.updated",
        {
            "symbol": payload.symbol,
            "focus_source": payload.focus_source,
            "signal_id": payload.signal_id,
        },
    )
    return snapshot
