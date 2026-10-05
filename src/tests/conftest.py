import asyncio
import os
import warnings

import pytest

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("REDIS_URL", "memory://")

from src import app
from src.db.main import get_session
from src.db.models import Base


@pytest.fixture(autouse=True)
def use_memory_token_blocklist(monkeypatch):
    from src.db import redis

    redis._memory_blocklist.clear()
    monkeypatch.setattr(redis, "token_blocklist", None)
    monkeypatch.setattr("src.auth.dependencies.token_in_blocklist", redis.token_in_blocklist)
    monkeypatch.setattr("src.auth.routes.add_jti_to_blocklist", redis.add_jti_to_blocklist)


@pytest.fixture
def session_factory(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    yield factory
    asyncio.run(engine.dispose())


@pytest.fixture
def test_client(session_factory):
    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def signup_payload():
    return {
        "first_name": "John",
        "last_name": "Doe",
        "username": "johndoe",
        "email": "john@example.com",
        "password": "testpass123",
    }


@pytest.fixture
def authenticated_headers(test_client, session_factory, signup_payload, monkeypatch):
    from sqlalchemy import select

    from src.auth import routes
    from src.db.models import User

    monkeypatch.setattr(routes.send_email, "delay", lambda *args, **kwargs: None)
    response = test_client.post("/api/v1/auth/signup", json=signup_payload)
    assert response.status_code == 201

    async def verify_user():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == signup_payload["email"]))
            user.is_verified = True
            await session.commit()

    asyncio.run(verify_user())
    login = test_client.post(
        "/api/v1/auth/login",
        json={"email": signup_payload["email"], "password": signup_payload["password"]},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
