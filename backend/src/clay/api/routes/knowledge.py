from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from clay.api.dependencies import get_db_session, get_knowledge_service
from clay.knowledge.models import KnowledgeCreateCommand
from clay.knowledge.service import KnowledgeService


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/overview")
async def get_knowledge_overview(
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    query: Annotated[str | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    return service.build_snapshot(session, query=query, category=category).model_dump(
        mode="json"
    )


@router.post("/items")
async def create_knowledge_item(
    command: KnowledgeCreateCommand,
    session: Annotated[Session, Depends(get_db_session)],
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> dict[str, object]:
    return service.create_item(session, command).model_dump(mode="json")
