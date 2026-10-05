TAGS_PREFIX = "/api/v1/tags"
BOOKS_PREFIX = "/api/v1/books"


def _book_payload():
    return {
        "title": "Tagged Book",
        "author": "Test Author",
        "publisher": "Test Publications",
        "published_date": "2024-12-10",
        "language": "English",
        "page_count": 215,
    }


def test_create_and_list_tags(test_client, authenticated_headers):
    created = test_client.post(TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers)

    assert created.status_code == 201
    assert created.json()["name"] == "fiction"

    response = test_client.get(TAGS_PREFIX + "/", headers=authenticated_headers)
    assert response.status_code == 200
    assert [tag["name"] for tag in response.json()] == ["fiction"]


def test_duplicate_tag_name_is_rejected(test_client, authenticated_headers):
    test_client.post(TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers)

    response = test_client.post(TAGS_PREFIX + "/", json={"name": "fiction"}, headers=authenticated_headers)

    assert response.status_code == 403
    assert response.json()["error_code"] == "tag_exists"


def test_add_tags_to_book(test_client, authenticated_headers):
    book_uid = test_client.post(
        BOOKS_PREFIX + "/", json=_book_payload(), headers=authenticated_headers
    ).json()["uid"]

    response = test_client.post(
        f"{TAGS_PREFIX}/book/{book_uid}/tags",
        json={"tags": [{"name": "fiction"}, {"name": "classic"}]},
        headers=authenticated_headers,
    )

    assert response.status_code == 200
    detail = test_client.get(f"{BOOKS_PREFIX}/{book_uid}", headers=authenticated_headers)
    assert {tag["name"] for tag in detail.json()["tags"]} == {"fiction", "classic"}


def test_update_tag(test_client, authenticated_headers):
    uid = test_client.post(
        TAGS_PREFIX + "/", json={"name": "ficton"}, headers=authenticated_headers
    ).json()["uid"]

    response = test_client.put(
        f"{TAGS_PREFIX}/{uid}", json={"name": "fiction"}, headers=authenticated_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "fiction"


def test_delete_tag_and_missing_tag_response(test_client, authenticated_headers):
    uid = test_client.post(
        TAGS_PREFIX + "/", json={"name": "temporary"}, headers=authenticated_headers
    ).json()["uid"]

    assert test_client.delete(f"{TAGS_PREFIX}/{uid}", headers=authenticated_headers).status_code == 204
    missing = test_client.delete(f"{TAGS_PREFIX}/{uid}", headers=authenticated_headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "tag_not_found"
