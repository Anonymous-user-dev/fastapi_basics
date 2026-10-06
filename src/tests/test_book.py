import asyncio
from pathlib import Path

import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase

from src import app
from src.celery_tasks import c_app
from src.config import settings
from src.db.models import Base, User

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


def test_create_and_list_books(test_client, authenticated_headers):
    created = test_client.post(BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers)

    assert created.status_code == 201
    assert created.json()["title"] == "Test Book"
    assert created.json()["uid"]

    response = test_client.get(BOOKS_PREFIX + "/", headers=authenticated_headers)
    assert response.status_code == 200
    assert [book["title"] for book in response.json()] == ["Test Book"]


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
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"
    assert response.json()["author"] == "Test Author"


def test_delete_book_removes_it(test_client, authenticated_headers):
    uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]

    response = test_client.delete(f"{BOOKS_PREFIX}/{uid}", headers=authenticated_headers)

    assert response.status_code == 204
    missing = test_client.get(f"{BOOKS_PREFIX}/{uid}", headers=authenticated_headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "book_not_found"


def test_create_book_validates_date_and_page_count(test_client, authenticated_headers):
    payload = _book_payload()
    payload["published_date"] = "not-a-date"
    payload["page_count"] = 0

    response = test_client.post(BOOKS_PREFIX + "/", json=payload, headers=authenticated_headers)

    assert response.status_code == 422


def test_books_require_authentication(test_client):
    assert test_client.get(BOOKS_PREFIX + "/").status_code in {401, 403}


def test_models_use_sqlalchemy_declarative_base():
    assert issubclass(Base, DeclarativeBase)
    assert set(Base.metadata.tables) == {"users", "books", "reviews", "tags", "book_tags"}
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
    from src.auth import routes

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
    monkeypatch.setattr(routes.send_email, "delay", lambda *args, **kwargs: None)
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


def test_application_infrastructure(test_client):
    assert app.openapi_url == "/api/v1/openapi.json"
    assert c_app.conf.broker_url == settings.REDIS_URL
    assert c_app.conf.result_backend == settings.REDIS_URL

    cors = test_client.options(
        BOOKS_PREFIX + "/",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )
    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "https://example.com"
    assert test_client.get(app.openapi_url, headers={"Host": "evil.example"}).status_code == 400


def test_celery_service_receives_application_configuration():
    compose = yaml.safe_load(Path("compose.yml").read_text())
    celery_environment = compose["services"]["celery"]["environment"]

    assert "DATABASE_URL" in celery_environment
    assert "JWT_SECRET" in celery_environment


def test_mail_message_is_html():
    from src.mail import create_message

    message = create_message(["reader@example.com"], "Welcome", "<h1>Hello</h1>")
    assert [recipient.email for recipient in message.recipients] == ["reader@example.com"]
    assert message.body == "<h1>Hello</h1>"


def test_migration_history_has_one_linear_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = list(scripts.walk_revisions())
    assert scripts.get_heads() == ["a04d79012711"]
    assert [revision.revision for revision in revisions] == [
        "a04d79012711",
        "dba4f311e944",
        "11d1f79aef4d",
    ]
