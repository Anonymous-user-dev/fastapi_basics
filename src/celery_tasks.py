import logging

from celery import Celery

c_app = Celery("bookly")
c_app.config_from_object("src.config")
logger = logging.getLogger(__name__)


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
