import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from src.db.models import OutboxEvent, User

AUTH_PREFIX = "/api/v1/auth"


def test_production_requires_a_strong_jwt_secret():
    from src.config import DEVELOPMENT_JWT_SECRET, Settings

    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ENVIRONMENT="production",
            JWT_SECRET="too-short",
            _env_file=None,
        )

    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ENVIRONMENT="production",
            JWT_SECRET=DEVELOPMENT_JWT_SECRET,
            _env_file=None,
        )


def test_production_requires_https_public_urls():
    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ENVIRONMENT="production",
            JWT_SECRET="a-production-secret-that-is-long-enough",
            PUBLIC_BASE_URL="http://books.example.com",
            _env_file=None,
        )


def test_signup_stores_verification_email_in_outbox(
    test_client, session_factory, signup_payload, monkeypatch
):
    from src.auth import routes

    monkeypatch.setattr(routes.settings, "PUBLIC_BASE_URL", "https://books.example.com")

    response = test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    assert response.status_code == 201

    async def load_event():
        async with session_factory() as session:
            return await session.scalar(select(OutboxEvent))

    event = asyncio.run(load_event())
    assert event is not None
    assert event.event_type == "email.send"
    assert event.status == "pending"
    assert event.attempts == 0
    assert event.payload["recipients"] == [signup_payload["email"]]
    assert event.payload["subject"] == "Verify Your email"
    assert (
        'href="https://books.example.com/api/v1/auth/verify/'
        in event.payload["body"]
    )


def test_user_and_outbox_event_roll_back_together(session_factory, signup_payload):
    from src.auth.schemas import UserCreateModel
    from src.auth.service import UserService
    from src.errors import UserAlreadyExists

    async def create_duplicate_user():
        service = UserService()
        user_data = UserCreateModel(**signup_payload)

        async with session_factory() as session:
            await service.create_user(
                user_data,
                session,
                outbox_events=[
                    OutboxEvent(event_type="email.send", payload={"attempt": 1})
                ],
            )

            with pytest.raises(UserAlreadyExists):
                await service.create_user(
                    user_data,
                    session,
                    outbox_events=[
                        OutboxEvent(event_type="email.send", payload={"attempt": 2})
                    ],
                )

            return await session.scalar(
                select(func.count()).select_from(OutboxEvent)
            )

    assert asyncio.run(create_duplicate_user()) == 1


def _disable_email(monkeypatch):
    from src import celery_tasks

    monkeypatch.setattr(celery_tasks.send_email, "delay", lambda *args, **kwargs: None)


def _set_verified(session_factory, email: str):
    async def update_user():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            user.is_verified = True
            await session.commit()

    asyncio.run(update_user())


def _is_verified(session_factory, email: str) -> bool:
    async def load_value():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            return user.is_verified

    return asyncio.run(load_value())


def test_signup_persists_user_without_exposing_password_hash(
    test_client, session_factory, signup_payload, monkeypatch
):
    _disable_email(monkeypatch)

    response = test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "john@example.com"
    assert "password_hash" not in response.json()["user"]

    async def load_user():
        async with session_factory() as session:
            return await session.scalar(select(User).where(User.email == "john@example.com"))

    user = asyncio.run(load_user())
    assert user is not None
    assert user.password_hash != signup_payload["password"]


def test_signup_rejects_duplicate_email(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    assert test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload).status_code == 201

    response = test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    assert response.status_code == 403
    assert response.json()["error_code"] == "user_exists"


def test_signup_rejects_duplicate_username(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    assert test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload).status_code == 201
    duplicate_username = {**signup_payload, "email": "other@example.com"}

    response = test_client.post(f"{AUTH_PREFIX}/signup", json=duplicate_username)

    assert response.status_code == 403
    assert response.json()["error_code"] == "user_exists"


def test_signup_succeeds_when_email_queue_is_unavailable(
    test_client, session_factory, signup_payload, monkeypatch
):
    from src import celery_tasks

    def unavailable_queue(*args, **kwargs):
        raise ConnectionError("message broker unavailable")

    monkeypatch.setattr(celery_tasks.send_email, "delay", unavailable_queue)

    response = test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    assert response.status_code == 201

    async def load_user():
        async with session_factory() as session:
            return await session.scalar(
                select(User).where(User.email == signup_payload["email"])
            )

    assert asyncio.run(load_user()) is not None


def test_login_returns_access_and_refresh_tokens(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    response = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]


def test_login_rejects_wrong_password(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    response = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": "incorrect-password"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_email_or_password"


def test_login_rate_limit_blocks_repeated_attempts(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    login_data = {"email": signup_payload["email"], "password": "incorrect-password"}

    responses = [
        test_client.post(f"{AUTH_PREFIX}/login", json=login_data)
        for _ in range(6)
    ]

    assert [response.status_code for response in responses[:5]] == [400] * 5
    assert responses[5].status_code == 429
    assert responses[5].json()["error_code"] == "rate_limit_exceeded"


def test_rate_limiter_uses_commands_supported_by_redis_6(monkeypatch):
    from src.db import redis

    class RedisSixCompatibleClient:
        def __init__(self):
            self.count = 0

        async def eval(self, script, number_of_keys, key, window_seconds):
            assert number_of_keys == 1
            assert key == "rate:login:client"
            assert window_seconds == 60
            self.count += 1
            return self.count

    redis_client = RedisSixCompatibleClient()
    monkeypatch.setattr(redis, "token_blocklist", redis_client)

    results = [
        asyncio.run(redis.rate_limit_allows("login:client", limit=2, window_seconds=60))
        for _ in range(3)
    ]

    assert results == [True, True, False]


def test_verification_token_marks_account_verified(test_client, session_factory, signup_payload, monkeypatch):
    from src.auth.utils import create_verification_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_verification_token({"email": signup_payload["email"]})

    response = test_client.get(f"{AUTH_PREFIX}/verify/{token}")

    assert response.status_code == 200
    assert _is_verified(session_factory, signup_payload["email"]) is True


def test_me_requires_verified_account(test_client, session_factory, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    login = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert test_client.get(f"{AUTH_PREFIX}/me", headers=headers).status_code == 403

    _set_verified(session_factory, signup_payload["email"])
    response = test_client.get(f"{AUTH_PREFIX}/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == signup_payload["email"]


def test_refresh_endpoint_rejects_access_token_and_accepts_refresh_token(
    test_client, signup_payload, monkeypatch
):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    tokens = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    ).json()

    access_response = test_client.get(
        f"{AUTH_PREFIX}/refresh_token",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    refresh_response = test_client.get(
        f"{AUTH_PREFIX}/refresh_token",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert access_response.status_code == 403
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]
    assert refresh_response.json()["refresh_token"]

    reused_refresh = test_client.get(
        f"{AUTH_PREFIX}/refresh_token",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert reused_refresh.status_code == 401
    assert reused_refresh.json()["error_code"] == "token_revoked"


def test_password_reset_changes_login_password(test_client, signup_payload, monkeypatch):
    from src.auth.utils import create_password_reset_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_password_reset_token({"email": signup_payload["email"]})

    response = test_client.post(
        f"{AUTH_PREFIX}/password-reset-confirm/{token}",
        json={"new_password": "new-password", "confirm_new_password": "new-password"},
    )

    assert response.status_code == 200
    login = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": "new-password"},
    )
    assert login.status_code == 200


def test_password_reset_token_cannot_be_reused(test_client, signup_payload, monkeypatch):
    from src.auth.utils import create_password_reset_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_password_reset_token({"email": signup_payload["email"]})
    first_reset = {
        "new_password": "first-password",
        "confirm_new_password": "first-password",
    }
    second_reset = {
        "new_password": "second-password",
        "confirm_new_password": "second-password",
    }

    first_response = test_client.post(
        f"{AUTH_PREFIX}/password-reset-confirm/{token}", json=first_reset
    )
    second_response = test_client.post(
        f"{AUTH_PREFIX}/password-reset-confirm/{token}", json=second_reset
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 401
    assert second_response.json()["error_code"] == "token_revoked"


def test_verification_token_cannot_reset_password(test_client, signup_payload, monkeypatch):
    from src.auth.utils import create_verification_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_verification_token({"email": signup_payload["email"]})

    response = test_client.post(
        f"{AUTH_PREFIX}/password-reset-confirm/{token}",
        json={"new_password": "new-password", "confirm_new_password": "new-password"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


def test_password_reset_token_cannot_verify_account(test_client, signup_payload, monkeypatch):
    from src.auth.utils import create_password_reset_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_password_reset_token({"email": signup_payload["email"]})

    response = test_client.get(f"{AUTH_PREFIX}/verify/{token}")

    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"


def test_logout_revokes_access_token(test_client, session_factory, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    _set_verified(session_factory, signup_payload["email"])
    token = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert test_client.get(f"{AUTH_PREFIX}/logout", headers=headers).status_code == 200
    response = test_client.get(f"{AUTH_PREFIX}/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error_code"] == "token_revoked"


def test_logout_revokes_refresh_token(test_client, signup_payload, monkeypatch):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    tokens = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    ).json()

    test_client.get(
        f"{AUTH_PREFIX}/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    response = test_client.get(
        f"{AUTH_PREFIX}/refresh_token",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "token_revoked"


def test_regular_user_cannot_use_manual_mail_endpoint(
    test_client, authenticated_headers, monkeypatch
):
    _disable_email(monkeypatch)

    response = test_client.post(
        f"{AUTH_PREFIX}/send_mail",
        json={"addresses": ["reader@example.com"]},
        headers=authenticated_headers,
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "insufficient_permissions"


def test_admin_can_use_manual_mail_endpoint(
    test_client, session_factory, signup_payload, monkeypatch
):
    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    async def promote_user():
        async with session_factory() as session:
            user = await session.scalar(
                select(User).where(User.email == signup_payload["email"])
            )
            user.is_verified = True
            user.role = "admin"
            await session.commit()

    asyncio.run(promote_user())
    login = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "email": signup_payload["email"],
            "password": signup_payload["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = test_client.post(
        f"{AUTH_PREFIX}/send_mail",
        json={"addresses": ["reader@example.com"]},
        headers=headers,
    )

    assert response.status_code == 200


def test_admin_is_told_when_manual_mail_cannot_be_queued(
    test_client, session_factory, signup_payload, monkeypatch
):
    from src import celery_tasks

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)

    async def promote_user():
        async with session_factory() as session:
            user = await session.scalar(
                select(User).where(User.email == signup_payload["email"])
            )
            user.is_verified = True
            user.role = "admin"
            await session.commit()

    asyncio.run(promote_user())
    login = test_client.post(
        f"{AUTH_PREFIX}/login",
        json={
            "email": signup_payload["email"],
            "password": signup_payload["password"],
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    def unavailable_queue(*args, **kwargs):
        raise ConnectionError("message broker unavailable")

    monkeypatch.setattr(celery_tasks.send_email, "delay", unavailable_queue)
    response = test_client.post(
        f"{AUTH_PREFIX}/send_mail",
        json={"addresses": ["reader@example.com"]},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "email_queue_unavailable"
