import logging
import socket
import uuid

from celery import Celery

c_app = Celery("bookly")
c_app.config_from_object("src.config")
logger = logging.getLogger(__name__)

c_app.conf.beat_schedule = {
    "relay-outbox-events": {
        "task": "src.celery_tasks.relay_outbox",
        "schedule": 5.0,
    }
}


@c_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_email(recipients: list[str], subject: str, body: str) -> None:
    from asgiref.sync import async_to_sync

    from src.mail import create_message, mail

    async_to_sync(mail.send_message)(create_message(recipients, subject, body))


def queue_email(recipients: list[str], subject: str, body: str) -> bool:
    """Queue an email without failing an already-completed API operation."""
    try:
        send_email.delay(recipients, subject, body)
    except Exception:
        logger.exception("Could not queue email with subject %r", subject)
        return False
    return True


@c_app.task(name="src.celery_tasks.relay_outbox")
def relay_outbox(batch_size: int = 25) -> dict[str, int]:
    from asgiref.sync import async_to_sync

    from src.db.main import session_factory
    from src.mail import create_message, mail
    from src.outbox import relay_outbox_events

    async def deliver_email(recipients: list[str], subject: str, body: str) -> None:
        await mail.send_message(create_message(recipients, subject, body))

    worker_id = f"{socket.gethostname()}:{uuid.uuid4()}"
    return async_to_sync(relay_outbox_events)(
        session_factory,
        deliver_email,
        worker_id=worker_id,
        batch_size=batch_size,
    )
