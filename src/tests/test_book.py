import asyncio
import json
import logging
import uuid
from pathlib import Path

import pytest
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import DeclarativeBase

from src import app
from src.celery_tasks import c_app
from src.config import settings
from src.db.models import Base, User
from src.db.models import Book as BookModel

BOOKS_PREFIX = "/api/v1/books"
TAGS_PREFIX = "/api/v1/tags"
REVIEWS_PREFIX = "/api/v1/reviews"


def _book_payload(title="Test Book"):
    return {
        "title": title,
        "author": "Test Author",
        "publisher": "Test Publications",
        "published_date": "2024-12-10",
        "language": "English",
        "page_count": 215,
    }


def _headers_for_new_user(test_client, session_factory, monkeypatch, *, role="user"):
    from src import celery_tasks

    user_data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "username": "janedoe",
        "email": "jane@example.com",
        "password": "testpass123",
    }
    monkeypatch.setattr(celery_tasks.send_email, "delay", lambda *args, **kwargs: None)
    assert test_client.post("/api/v1/auth/signup", json=user_data).status_code == 201

    async def activate_user():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == user_data["email"]))
            user.is_verified = True
            user.role = role
            await session.commit()

    asyncio.run(activate_user())
    token = test_client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_books(test_client, authenticated_headers):
    created = test_client.post(BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers)

    assert created.status_code == 201
    assert created.json()["title"] == "Test Book"
    assert created.json()["uid"]

    response = test_client.get(BOOKS_PREFIX + "/", headers=authenticated_headers)
    assert response.status_code == 200
    assert [book["title"] for book in response.json()] == ["Test Book"]


def test_book_creation_replays_the_result_for_the_same_idempotency_key(
    test_client,
    authenticated_headers,
    session_factory,
):
    headers = {**authenticated_headers, "Idempotency-Key": "create-book-123"}

    first = test_client.post(BOOKS_PREFIX + "/", json=_book_payload(), headers=headers)
    replay = test_client.post(BOOKS_PREFIX + "/", json=_book_payload(), headers=headers)

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert replay.headers["Idempotent-Replayed"] == "true"

    async def count_books():
        async with session_factory() as session:
            return await session.scalar(select(func.count()).select_from(BookModel))

    assert asyncio.run(count_books()) == 1


def test_book_creation_rejects_key_reuse_with_different_payload(
    test_client,
    authenticated_headers,
):
    headers = {**authenticated_headers, "Idempotency-Key": "create-book-123"}
    assert test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload("First request"),
        headers=headers,
    ).status_code == 201

    conflict = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload("Changed request"),
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "idempotency_key_conflict"


def test_book_list_supports_bounded_pagination(test_client, authenticated_headers):
    for title in ("First", "Second", "Third"):
        assert test_client.post(
            BOOKS_PREFIX + "/",
            json=_book_payload(title),
            headers=authenticated_headers,
        ).status_code == 201

    first_page = test_client.get(
        BOOKS_PREFIX + "/?limit=1&offset=0", headers=authenticated_headers
    )
    second_page = test_client.get(
        BOOKS_PREFIX + "/?limit=1&offset=1", headers=authenticated_headers
    )
    excessive_limit = test_client.get(
        BOOKS_PREFIX + "/?limit=101", headers=authenticated_headers
    )

    assert len(first_page.json()) == 1
    assert len(second_page.json()) == 1
    assert first_page.json()[0]["uid"] != second_page.json()[0]["uid"]
    assert excessive_limit.status_code == 422


def test_book_detail_includes_reviews_and_tags(test_client, authenticated_headers):
    uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]

    response = test_client.get(f"{BOOKS_PREFIX}/{uid}", headers=authenticated_headers)

    assert response.status_code == 200
    assert response.json()["reviews"] == []
    assert response.json()["tags"] == []


def test_user_submissions_only_return_that_users_books(
    test_client, authenticated_headers, signup_payload
):
    created = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()
    profile = test_client.get("/api/v1/auth/me", headers=authenticated_headers).json()

    response = test_client.get(
        f"{BOOKS_PREFIX}/user/{profile['uid']}", headers=authenticated_headers
    )

    assert response.status_code == 200
    assert [book["uid"] for book in response.json()] == [created["uid"]]


def test_patch_updates_only_supplied_book_fields(test_client, authenticated_headers):
    created = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()

    response = test_client.patch(
        f"{BOOKS_PREFIX}/{created['uid']}",
        json={"title": "Updated title"},
        headers={**authenticated_headers, "If-Match": '"1"'},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"
    assert response.json()["author"] == "Test Author"


def test_stale_book_update_cannot_overwrite_a_newer_version(
    test_client,
    authenticated_headers,
):
    created = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload(),
        headers=authenticated_headers,
    )
    book = created.json()
    version_headers = {**authenticated_headers, "If-Match": created.headers["ETag"]}

    updated = test_client.patch(
        f"{BOOKS_PREFIX}/{book['uid']}",
        json={"title": "First writer"},
        headers=version_headers,
    )
    stale = test_client.patch(
        f"{BOOKS_PREFIX}/{book['uid']}",
        json={"title": "Stale writer"},
        headers=version_headers,
    )
    stale_delete = test_client.delete(
        f"{BOOKS_PREFIX}/{book['uid']}",
        headers=version_headers,
    )

    assert book["version"] == 1
    assert created.headers["ETag"] == '"1"'
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.headers["ETag"] == '"2"'
    assert stale.status_code == 412
    assert stale.json()["error_code"] == "stale_book_version"
    assert stale_delete.status_code == 412

    current = test_client.get(
        f"{BOOKS_PREFIX}/{book['uid']}",
        headers=authenticated_headers,
    )
    assert current.json()["title"] == "First writer"
    assert current.json()["version"] == 2


def test_book_write_requires_a_version_precondition(
    test_client,
    authenticated_headers,
):
    created = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload(),
        headers=authenticated_headers,
    ).json()

    response = test_client.patch(
        f"{BOOKS_PREFIX}/{created['uid']}",
        json={"title": "Unconditional update"},
        headers=authenticated_headers,
    )

    assert response.status_code == 428
    assert response.json()["error_code"] == "precondition_required"


def test_patch_rejects_null_for_required_book_fields(test_client, authenticated_headers):
    created = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()

    response = test_client.patch(
        f"{BOOKS_PREFIX}/{created['uid']}",
        json={"title": None},
        headers=authenticated_headers,
    )

    assert response.status_code == 422


def test_delete_book_removes_it(test_client, authenticated_headers):
    uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]

    response = test_client.delete(
        f"{BOOKS_PREFIX}/{uid}",
        headers={**authenticated_headers, "If-Match": '"1"'},
    )

    assert response.status_code == 204
    missing = test_client.get(f"{BOOKS_PREFIX}/{uid}", headers=authenticated_headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "book_not_found"


def test_another_user_cannot_update_or_delete_a_book(
    test_client, authenticated_headers, session_factory, monkeypatch
):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]
    other_user_headers = _headers_for_new_user(
        test_client, session_factory, monkeypatch
    )

    update = test_client.patch(
        f"{BOOKS_PREFIX}/{book_uid}",
        json={"title": "Someone else's edit"},
        headers=other_user_headers,
    )
    delete = test_client.delete(
        f"{BOOKS_PREFIX}/{book_uid}", headers=other_user_headers
    )

    assert update.status_code == 403
    assert update.json()["error_code"] == "insufficient_permissions"
    assert delete.status_code == 403


def test_admin_can_update_and_delete_any_book(
    test_client, authenticated_headers, session_factory, monkeypatch
):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]
    admin_headers = _headers_for_new_user(
        test_client, session_factory, monkeypatch, role="admin"
    )

    update = test_client.patch(
        f"{BOOKS_PREFIX}/{book_uid}",
        json={"title": "Admin edit"},
        headers={**admin_headers, "If-Match": '"1"'},
    )
    delete = test_client.delete(
        f"{BOOKS_PREFIX}/{book_uid}",
        headers={**admin_headers, "If-Match": '"2"'},
    )

    assert update.status_code == 200
    assert update.json()["title"] == "Admin edit"
    assert delete.status_code == 204


def test_create_book_validates_date_and_page_count(test_client, authenticated_headers):
    payload = _book_payload()
    payload["published_date"] = "not-a-date"
    payload["page_count"] = 0

    response = test_client.post(BOOKS_PREFIX + "/", json=payload, headers=authenticated_headers)

    assert response.status_code == 422


def test_books_require_authentication(test_client):
    assert test_client.get(BOOKS_PREFIX + "/").status_code in {401, 403}


def test_request_id_is_propagated_and_logged(test_client, caplog):
    caplog.set_level(logging.INFO, logger="bookly.access")

    response = test_client.get(
        "/api/v1/openapi.json",
        headers={
            "X-Request-ID": "checkout-7f31",
            "Authorization": "Bearer do-not-log-this",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "checkout-7f31"
    access_log = json.loads(caplog.records[-1].message)
    assert access_log["event"] == "http.request.completed"
    assert access_log["request_id"] == "checkout-7f31"
    assert access_log["method"] == "GET"
    assert access_log["path"] == "/api/v1/openapi.json"
    assert access_log["status_code"] == 200
    assert access_log["duration_ms"] >= 0
    assert "do-not-log-this" not in caplog.text


def test_invalid_request_id_is_replaced(test_client):
    response = test_client.get(
        "/api/v1/openapi.json",
        headers={"X-Request-ID": "not a safe request id"},
    )

    assert response.status_code == 200
    assert uuid.UUID(response.headers["X-Request-ID"])


def test_liveness_and_readiness_report_service_health(test_client):
    live = test_client.get("/health/live")
    ready = test_client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200, ready.json()
    assert ready.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_readiness_fails_closed_when_a_dependency_is_unavailable(
    test_client,
    monkeypatch,
):
    from src import health

    async def unavailable_redis():
        raise ConnectionError("secret infrastructure details")

    monkeypatch.setattr(health, "check_redis", unavailable_redis)

    response = test_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "redis": "unavailable"},
    }
    assert "secret infrastructure details" not in response.text


def test_models_use_sqlalchemy_declarative_base():
    assert issubclass(Base, DeclarativeBase)
    assert set(Base.metadata.tables) == {
        "users",
        "books",
        "reviews",
        "tags",
        "book_tags",
        "outbox_events",
        "idempotency_records",
    }
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)


def test_create_list_and_delete_tags(test_client, authenticated_headers):
    created = test_client.post(
        TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers
    )
    assert created.status_code == 201
    assert [tag["name"] for tag in test_client.get(
        TAGS_PREFIX + "/", headers=authenticated_headers
    ).json()] == ["fiction"]

    uid = created.json()["uid"]
    assert test_client.delete(f"{TAGS_PREFIX}/{uid}", headers=authenticated_headers).status_code == 204
    assert test_client.delete(f"{TAGS_PREFIX}/{uid}", headers=authenticated_headers).status_code == 404


def test_duplicate_tag_name_is_rejected(test_client, authenticated_headers):
    test_client.post(TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers)
    response = test_client.post(
        TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "tag_exists"


def test_blank_tag_name_is_rejected(test_client, authenticated_headers):
    response = test_client.post(
        TAGS_PREFIX + "/", json={"name": "   "}, headers=authenticated_headers
    )
    assert response.status_code == 422


def test_add_tags_to_book(test_client, authenticated_headers):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload("Tagged Book"), headers=authenticated_headers
    ).json()["uid"]
    response = test_client.post(
        f"{TAGS_PREFIX}/book/{book_uid}/tags",
        json={"tags": [{"name": "fiction"}, {"name": "classic"}]},
        headers=authenticated_headers,
    )
    assert response.status_code == 200
    detail = test_client.get(f"{BOOKS_PREFIX}/{book_uid}", headers=authenticated_headers)
    assert {tag["name"] for tag in detail.json()["tags"]} == {"fiction", "classic"}


def test_repeated_tag_in_one_request_is_added_once(test_client, authenticated_headers):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload("Tagged Book"), headers=authenticated_headers
    ).json()["uid"]

    response = test_client.post(
        f"{TAGS_PREFIX}/book/{book_uid}/tags",
        json={"tags": [{"name": "fiction"}, {"name": "fiction"}]},
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    assert [tag["name"] for tag in response.json()["tags"]] == ["fiction"]


def test_another_user_cannot_add_tags_to_a_book(
    test_client, authenticated_headers, session_factory, monkeypatch
):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload("Owner's Book"),
        headers=authenticated_headers,
    ).json()["uid"]
    other_user_headers = _headers_for_new_user(
        test_client, session_factory, monkeypatch
    )

    response = test_client.post(
        f"{TAGS_PREFIX}/book/{book_uid}/tags",
        json={"tags": [{"name": "unauthorized"}]},
        headers=other_user_headers,
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "insufficient_permissions"
    detail = test_client.get(f"{BOOKS_PREFIX}/{book_uid}", headers=authenticated_headers)
    assert detail.json()["tags"] == []


def test_invalid_role_cannot_manage_an_owned_book(
    test_client, authenticated_headers, session_factory
):
    from src.errors import InsufficientPermission
    from src.tags.schemas import TagAddModel
    from src.tags.service import TagService

    book_uid = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload("Role Protected Book"),
        headers=authenticated_headers,
    ).json()["uid"]

    async def add_tag_with_invalid_role():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == "john@example.com"))
            user.role = "editor"
            await session.commit()

            with pytest.raises(InsufficientPermission):
                await TagService().add_tags_to_book(
                    uuid.UUID(book_uid),
                    TagAddModel(tags=[{"name": "security"}]),
                    user,
                    session,
                )

    asyncio.run(add_tag_with_invalid_role())


def test_add_and_get_five_star_review(test_client, authenticated_headers):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload("Reviewed Book"), headers=authenticated_headers
    ).json()["uid"]
    created = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book_uid}",
        json={"rating": 5, "review_text": "Excellent"},
        headers=authenticated_headers,
    )
    assert created.status_code == 201
    response = test_client.get(
        f"{REVIEWS_PREFIX}/{created.json()['uid']}", headers=authenticated_headers
    )
    assert response.status_code == 200
    assert response.json()["rating"] == 5


def test_review_rating_is_bounded(test_client, authenticated_headers):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload("Reviewed Book"), headers=authenticated_headers
    ).json()["uid"]
    for rating in (0, 6):
        response = test_client.post(
            f"{REVIEWS_PREFIX}/book/{book_uid}",
            json={"rating": rating, "review_text": "Invalid"},
            headers=authenticated_headers,
        )
        assert response.status_code == 422


def test_another_user_cannot_delete_review(
    test_client, authenticated_headers, session_factory, monkeypatch
):
    from src import celery_tasks

    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload("Reviewed Book"), headers=authenticated_headers
    ).json()["uid"]
    review_uid = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book_uid}",
        json={"rating": 4, "review_text": "Good"},
        headers=authenticated_headers,
    ).json()["uid"]
    second_user = {
        "first_name": "Jane",
        "last_name": "Doe",
        "username": "janedoe",
        "email": "jane@example.com",
        "password": "testpass123",
    }
    monkeypatch.setattr(celery_tasks.send_email, "delay", lambda *args, **kwargs: None)
    assert test_client.post("/api/v1/auth/signup", json=second_user).status_code == 201

    async def verify_second_user():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == second_user["email"]))
            user.is_verified = True
            await session.commit()

    asyncio.run(verify_second_user())
    token = test_client.post(
        "/api/v1/auth/login",
        json={"email": second_user["email"], "password": second_user["password"]},
    ).json()["access_token"]
    response = test_client.delete(
        f"{REVIEWS_PREFIX}/{review_uid}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_admin_can_delete_another_users_review(
    test_client, authenticated_headers, session_factory, monkeypatch
):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/",
        json=_book_payload("Reviewed Book"),
        headers=authenticated_headers,
    ).json()["uid"]
    review_uid = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book_uid}",
        json={"rating": 4, "review_text": "Good"},
        headers=authenticated_headers,
    ).json()["uid"]
    admin_headers = _headers_for_new_user(
        test_client, session_factory, monkeypatch, role="admin"
    )

    response = test_client.delete(
        f"{REVIEWS_PREFIX}/{review_uid}", headers=admin_headers
    )

    assert response.status_code == 204
    missing = test_client.get(
        f"{REVIEWS_PREFIX}/{review_uid}", headers=admin_headers
    )
    assert missing.status_code == 404


def test_application_infrastructure(test_client):
    assert app.openapi_url == "/api/v1/openapi.json"
    assert c_app.conf.broker_url == settings.REDIS_URL
    assert c_app.conf.result_backend == settings.REDIS_URL

    cors = test_client.options(
        BOOKS_PREFIX + "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "http://localhost:3000"

    untrusted_cors = test_client.options(
        BOOKS_PREFIX + "/",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in untrusted_cors.headers
    assert test_client.get(app.openapi_url, headers={"Host": "evil.example"}).status_code == 400


def test_celery_service_receives_application_configuration():
    compose = yaml.safe_load(Path("compose.yml").read_text())
    celery_environment = compose["services"]["celery"]["environment"]

    assert "DATABASE_URL" in celery_environment
    assert "JWT_SECRET" in celery_environment


def test_outbox_relay_is_scheduled_and_has_database_access():
    schedule = c_app.conf.beat_schedule["relay-outbox-events"]
    compose = yaml.safe_load(Path("compose.yml").read_text())

    assert schedule["task"] == "src.celery_tasks.relay_outbox"
    assert schedule["schedule"] == 5.0
    assert "celery-beat" in compose["services"]
    assert "db" in compose["services"]["celery"]["depends_on"]
    assert "db" in compose["services"]["celery-beat"]["depends_on"]


def test_compose_waits_for_healthy_dependencies():
    services = yaml.safe_load(Path("compose.yml").read_text())["services"]

    assert services["web"]["healthcheck"]
    assert services["db"]["healthcheck"]
    assert services["redis"]["healthcheck"]
    for service_name in ("web", "celery", "celery-beat"):
        assert services[service_name]["depends_on"]["db"]["condition"] == "service_healthy"
        assert (
            services[service_name]["depends_on"]["redis"]["condition"]
            == "service_healthy"
        )


def test_mail_message_is_html():
    from src.mail import create_message

    message = create_message(["reader@example.com"], "Welcome", "<h1>Hello</h1>")
    assert [recipient.email for recipient in message.recipients] == ["reader@example.com"]
    assert message.body == "<h1>Hello</h1>"


def test_migration_history_has_one_linear_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = list(scripts.walk_revisions())
    assert scripts.get_heads() == ["c28f406bd173"]
    assert [revision.revision for revision in revisions] == [
        "c28f406bd173",
        "9c3a74e5b821",
        "6f47c8e912ab",
        "a04d79012711",
        "dba4f311e944",
        "11d1f79aef4d",
    ]
