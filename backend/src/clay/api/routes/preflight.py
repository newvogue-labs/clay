from fastapi import APIRouter

from clay.bootstrap import preflight_service

router = APIRouter(prefix="/preflight", tags=["preflight"])


@router.get("")
async def get_preflight_result() -> dict[str, object]:
    return preflight_service.run().model_dump(mode="json")
