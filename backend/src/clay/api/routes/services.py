from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from clay.bootstrap import audit_writer, event_bus, registry, supervisor
from clay.services.supervisor import ServiceActionNotAllowedError


router = APIRouter(prefix="/services", tags=["services"])


class ServiceActionRequest(BaseModel):
    action: Literal["start", "stop", "restart"]


@router.get("")
async def list_services() -> dict[str, object]:
    return {
        "items": [
            {
                "service_id": service.service_id,
                "service_type": service.service_type,
                "criticality": service.criticality.value,
                "startup_policy": service.startup_policy,
                "status": service.status.value,
                "last_error": service.last_error,
                "allowed_actions": list(supervisor.allowed_actions(service.service_id)),
            }
            for service in registry.list_services()
        ],
    }


@router.post("/{service_id}/actions")
async def run_service_action(
    service_id: str,
    payload: ServiceActionRequest,
) -> dict[str, object]:
    try:
        if payload.action == "start":
            service = supervisor.start(service_id)
        elif payload.action == "stop":
            service = supervisor.stop(service_id)
        else:
            service = supervisor.restart(service_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown service: {service_id}"
        ) from exc
    except ServiceActionNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    audit_writer.write(
        "service.action",
        {
            "service_id": service.service_id,
            "action": payload.action,
            "status": service.status.value,
        },
    )
    event_bus.publish(
        "service.updated",
        {
            "service_id": service.service_id,
            "action": payload.action,
            "status": service.status.value,
        },
    )
    return {
        "service_id": service.service_id,
        "status": service.status.value,
    }
