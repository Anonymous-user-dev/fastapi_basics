import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.db.models import OutboxEvent, utc_now
from src.observability import log_json

EmailSender = Callable[[list[str], str, str], Awaitable[None]]
logger = logging.getLogger(__name__)

LEASE_DURATION = timedelta(minutes=5)
MAX_RETRY_DELAY_SECONDS = 300


async def claim_outbox_events(
    session_factory: async_sessionmaker[AsyncSession],
    worker_id: str,
    *,
    batch_size: int = 25,
) -> list[UUID]:
    now = utc_now()
    eligible = and_(
        OutboxEvent.available_at <= now,
        or_(
            OutboxEvent.status == "pending",
            and_(
                OutboxEvent.status == "processing",
                OutboxEvent.locked_until < now,
            ),
        ),
    )

    async with session_factory() as session:
        statement = (
            select(OutboxEvent.uid)
            .where(eligible)
            .order_by(OutboxEvent.created_at, OutboxEvent.uid)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        event_ids = list(await session.scalars(statement))
        if not event_ids:
            return []

        await session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.uid.in_(event_ids))
            .values(
                status="processing",
                attempts=OutboxEvent.attempts + 1,
                locked_by=worker_id,
                locked_until=now + LEASE_DURATION,
            )
        )
        await session.commit()
        return event_ids


async def _load_claimed_event(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    worker_id: str,
) -> tuple[str, dict] | None:
    async with session_factory() as session:
        row = await session.execute(
            select(OutboxEvent.event_type, OutboxEvent.payload).where(
                OutboxEvent.uid == event_id,
                OutboxEvent.status == "processing",
                OutboxEvent.locked_by == worker_id,
            )
        )
        return row.one_or_none()


async def _mark_processed(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    worker_id: str,
) -> bool:
    async with session_factory() as session:
        result = await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.uid == event_id,
                OutboxEvent.status == "processing",
                OutboxEvent.locked_by == worker_id,
            )
            .values(
                status="processed",
                processed_at=utc_now(),
                locked_by=None,
                locked_until=None,
                last_error=None,
            )
        )
        await session.commit()
        return result.rowcount == 1


async def _release_for_retry(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    worker_id: str,
    error: Exception,
) -> bool:
    async with session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.uid == event_id,
                OutboxEvent.status == "processing",
                OutboxEvent.locked_by == worker_id,
            )
        )
        if event is None:
            return False

        if event.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
            event.status = "failed"
        else:
            retry_delay = min(2**event.attempts, MAX_RETRY_DELAY_SECONDS)
            event.status = "pending"
            event.available_at = utc_now() + timedelta(seconds=retry_delay)
        event.locked_by = None
        event.locked_until = None
        event.last_error = str(error)[:2000]
        await session.commit()
        return True


async def _deliver_event(
    session_factory: async_sessionmaker[AsyncSession],
    sender: EmailSender,
    event_id: UUID,
    worker_id: str,
) -> bool:
    claimed_event = await _load_claimed_event(session_factory, event_id, worker_id)
    if claimed_event is None:
        return False

    event_type, payload = claimed_event
    try:
        if event_type != "email.send":
            raise ValueError(f"Unsupported outbox event type: {event_type}")
        await sender(payload["recipients"], payload["subject"], payload["body"])
    except Exception as error:  # noqa: BLE001 - every failure must release the lease
        log_json(
            logger,
            logging.ERROR,
            "outbox.delivery.failed",
            exc_info=True,
            event_id=event_id,
            worker_id=worker_id,
            error_type=type(error).__name__,
            error=str(error),
        )
        await _release_for_retry(session_factory, event_id, worker_id, error)
        return False

    return await _mark_processed(session_factory, event_id, worker_id)


async def relay_outbox_events(
    session_factory: async_sessionmaker[AsyncSession],
    sender: EmailSender,
    *,
    worker_id: str,
    batch_size: int = 25,
) -> dict[str, int]:
    event_ids = await claim_outbox_events(
        session_factory,
        worker_id,
        batch_size=batch_size,
    )
    processed = 0
    for event_id in event_ids:
        if await _deliver_event(session_factory, sender, event_id, worker_id):
            processed += 1

    return {
        "claimed": len(event_ids),
        "processed": processed,
        "failed": len(event_ids) - processed,
    }
