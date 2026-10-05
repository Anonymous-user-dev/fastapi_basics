BOOKS_PREFIX = "/api/v1/books"


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
