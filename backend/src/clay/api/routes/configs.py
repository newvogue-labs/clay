from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clay.bootstrap import audit_writer, config_loader, event_bus
from clay.config.loader import UnknownConfigScopeError


router = APIRouter(prefix="/configs", tags=["configs"])


class ConfigApplyRequest(BaseModel):
    config: dict[str, Any]


@router.get("")
async def get_configs() -> dict[str, object]:
    return {
        "config_dir": str(config_loader.paths.config_dir),
        "items": config_loader.snapshot(),
        "ui_mutable_scopes": config_loader.list_scopes(),
    }


@router.post("/{scope}")
async def apply_config(
    scope: str,
    payload: ConfigApplyRequest,
) -> dict[str, object]:
    try:
        updated = config_loader.apply_config(scope, payload.config)
    except UnknownConfigScopeError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown config scope: {scope}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_writer.write("config.applied", {"scope": scope})
    event_bus.publish("config.updated", {"scope": scope, "kind": "applied"})
    return {"scope": scope, "config": updated}


@router.post("/{scope}/restore")
async def restore_config(scope: str) -> dict[str, object]:
    try:
        restored_from = config_loader.restore_last_valid(scope)
        restored = config_loader.load_scope(scope).model_dump(mode="json")
    except UnknownConfigScopeError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown config scope: {scope}"
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_writer.write("config.restored", {"scope": scope})
    event_bus.publish("config.updated", {"scope": scope, "kind": "restored"})
    return {
        "scope": scope,
        "config": restored,
        "restored_from": str(restored_from),
    }
