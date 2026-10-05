from celery import Celery

c_app = Celery("bookly")
c_app.config_from_object("src.config")


@c_app.task()
def send_email(recipients: list[str], subject: str, body: str) -> None:
    from asgiref.sync import async_to_sync

    from src.mail import create_message, mail

    async_to_sync(mail.send_message)(create_message(recipients, subject, body))
