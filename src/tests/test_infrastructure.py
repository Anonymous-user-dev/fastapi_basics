from src import app
from src.celery_tasks import c_app
from src.config import settings


def test_application_exposes_versioned_documentation():
    assert app.title == "Bookly"
    assert app.openapi_url == "/api/v1/openapi.json"
    assert app.docs_url == "/api/v1/docs"
    assert app.redoc_url == "/api/v1/redoc"


def test_celery_uses_configured_redis_backend():
    assert c_app.conf.broker_url == settings.REDIS_URL
    assert c_app.conf.result_backend == settings.REDIS_URL


def test_mail_message_is_html_and_preserves_recipients():
    from src.mail import create_message

    message = create_message(["reader@example.com"], "Welcome", "<h1>Hello</h1>")

    assert [recipient.email for recipient in message.recipients] == ["reader@example.com"]
    assert message.subject == "Welcome"
    assert message.body == "<h1>Hello</h1>"


def test_cors_preflight_is_allowed(test_client):
    response = test_client.options(
        "/api/v1/books/",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"


def test_untrusted_host_is_rejected(test_client):
    response = test_client.get("/api/v1/openapi.json", headers={"Host": "evil.example"})
    assert response.status_code == 400
