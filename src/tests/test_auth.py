import asyncio

from sqlalchemy import select

from src.db.models import User

AUTH_PREFIX = "/api/v1/auth"


def _disable_email(monkeypatch):
    from src.auth import routes

    monkeypatch.setattr(routes.send_email, "delay", lambda *args, **kwargs: None)


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


def test_verification_token_marks_account_verified(test_client, session_factory, signup_payload, monkeypatch):
    from src.auth.utils import create_url_safe_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_url_safe_token({"email": signup_payload["email"]})

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


def test_password_reset_changes_login_password(test_client, signup_payload, monkeypatch):
    from src.auth.utils import create_url_safe_token

    _disable_email(monkeypatch)
    test_client.post(f"{AUTH_PREFIX}/signup", json=signup_payload)
    token = create_url_safe_token({"email": signup_payload["email"]})

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
