import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import RoleChecker, get_current_user
from src.db.main import get_session
from src.db.models import OutboxEvent, User, utc_now
from src.errors import OutboxEventNotFound
from src.observability import log_json

admin_router = APIRouter(prefix="/admin/outbox", tags=["admin"])
admin_role = RoleChecker(["admin"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0)]
logger = logging.getLogger(__name__)


class OutboxEventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    event_type: str
    status: str
    attempts: int
    available_at: datetime
    created_at: datetime
    processed_at: datetime | None
    last_error: str | None


@admin_router.get(
    "/dead-letters",
    response_model=list[OutboxEventSummary],
    dependencies=[Depends(admin_role)],
)
async def list_dead_letters(
    session: SessionDep,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> list[OutboxEvent]:
    result = await session.scalars(
        select(OutboxEvent)
        .where(OutboxEvent.status == "failed")
        .order_by(desc(OutboxEvent.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())


@admin_router.post(
    "/dead-letters/{event_uid}/replay",
    response_model=OutboxEventSummary,
    dependencies=[Depends(admin_role)],
)
async def replay_dead_letter(
    event_uid: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> OutboxEvent:
    event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.uid == event_uid,
            OutboxEvent.status == "failed",
        )
    )
    if event is None:
        raise OutboxEventNotFound()

    event.status = "pending"
    event.attempts = 0
    event.available_at = utc_now()
    event.processed_at = None
    event.locked_by = None
    event.locked_until = None
    event.last_error = None
    await session.commit()
    await session.refresh(event)
    log_json(
        logger,
        logging.INFO,
        "outbox.dead_letter.replayed",
        event_id=event.uid,
        admin_user_id=current_user.uid,
    )
    return event
