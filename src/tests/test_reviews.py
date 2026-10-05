import asyncio

from sqlalchemy import select

from src.db.models import User

REVIEWS_PREFIX = "/api/v1/reviews"
BOOKS_PREFIX = "/api/v1/books"


def _book_payload():
    return {
        "title": "Reviewed Book",
        "author": "Test Author",
        "publisher": "Test Publications",
        "published_date": "2024-12-10",
        "language": "English",
        "page_count": 215,
    }


def _create_book(test_client, headers):
    return test_client.post(BOOKS_PREFIX + "/", json=_book_payload(), headers=headers).json()


def test_add_and_get_review_with_five_star_rating(test_client, authenticated_headers):
    book = _create_book(test_client, authenticated_headers)

    created = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book['uid']}",
        json={"rating": 5, "review_text": "Excellent"},
        headers=authenticated_headers,
    )

    assert created.status_code == 201
    assert created.json()["rating"] == 5
    response = test_client.get(
        f"{REVIEWS_PREFIX}/{created.json()['uid']}", headers=authenticated_headers
    )
    assert response.status_code == 200
    assert response.json()["review_text"] == "Excellent"

    book_detail = test_client.get(f"{BOOKS_PREFIX}/{book['uid']}", headers=authenticated_headers)
    assert [review["uid"] for review in book_detail.json()["reviews"]] == [created.json()["uid"]]


def test_review_rating_must_be_between_one_and_five(test_client, authenticated_headers):
    book = _create_book(test_client, authenticated_headers)

    for invalid_rating in (0, 6):
        response = test_client.post(
            f"{REVIEWS_PREFIX}/book/{book['uid']}",
            json={"rating": invalid_rating, "review_text": "Invalid"},
            headers=authenticated_headers,
        )
        assert response.status_code == 422


def test_get_missing_review_returns_structured_404(test_client, authenticated_headers):
    response = test_client.get(
        f"{REVIEWS_PREFIX}/00000000-0000-0000-0000-000000000001",
        headers=authenticated_headers,
    )

    assert response.status_code == 404
    assert response.json()["error_code"] == "review_not_found"


def test_review_owner_can_delete_review(test_client, authenticated_headers):
    book = _create_book(test_client, authenticated_headers)
    review = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book['uid']}",
        json={"rating": 4, "review_text": "Good"},
        headers=authenticated_headers,
    ).json()

    response = test_client.delete(f"{REVIEWS_PREFIX}/{review['uid']}", headers=authenticated_headers)

    assert response.status_code == 204
    assert (
        test_client.get(f"{REVIEWS_PREFIX}/{review['uid']}", headers=authenticated_headers).status_code
        == 404
    )


def test_another_user_cannot_delete_review(
    test_client,
    authenticated_headers,
    session_factory,
    monkeypatch,
):
    from src.auth import routes

    book = _create_book(test_client, authenticated_headers)
    review = test_client.post(
        f"{REVIEWS_PREFIX}/book/{book['uid']}",
        json={"rating": 4, "review_text": "Good"},
        headers=authenticated_headers,
    ).json()
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
        f"{REVIEWS_PREFIX}/{review['uid']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_regular_user_cannot_list_all_reviews(test_client, authenticated_headers):
    response = test_client.get(REVIEWS_PREFIX + "/", headers=authenticated_headers)
    assert response.status_code == 401


def test_admin_can_list_all_reviews(
    test_client, authenticated_headers, session_factory, signup_payload
):
    book = _create_book(test_client, authenticated_headers)
    test_client.post(
        f"{REVIEWS_PREFIX}/book/{book['uid']}",
        json={"rating": 4, "review_text": "Good"},
        headers=authenticated_headers,
    )

    async def promote_user():
        async with session_factory() as session:
            user = await session.scalar(select(User).where(User.email == signup_payload["email"]))
            user.role = "admin"
            await session.commit()

    asyncio.run(promote_user())
    response = test_client.get(REVIEWS_PREFIX + "/", headers=authenticated_headers)

    assert response.status_code == 200
    assert [review["review_text"] for review in response.json()] == ["Good"]
