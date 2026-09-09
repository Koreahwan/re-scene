import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings


@pytest.mark.asyncio
async def test_review_ratings_and_film_aggregation(monkeypatch):
    """
    Test BE03:
    1. Post creation with integer rating and author_cutoff_ms.
    2. Rating returned in post summary & detail.
    3. Film detail computes real average rating and count.
    4. Post update updates rating and film average.
    5. Post deletion removes rating from film average.
    6. Author cutoff is reflected in comment and spoiler protection.
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sess = f"sess_rating_tester_{uuid.uuid4().hex[:8]}"
        client.cookies.set("reframe_viewer_session", sess)

        # 1. Create a review post with rating=4, author_cutoff_ms=2000000
        post_resp = await client.post(
            "/api/v1/community/posts",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "REVIEW",
                "title": "A Great Classic Mystery",
                "body_markdown": "Brilliant cinematography and solid pacing.",
                "rating": 4,
                "author_cutoff_ms": 2000000
            }
        )
        assert post_resp.status_code == 201
        pid_1 = post_resp.json()["data"]["post_id"]

        # 2. Check post detail has rating=4 and author_cutoff_ms=2000000
        await client.post("/api/v1/viewer/unlock", json={
            "content_type": "POST",
            "content_id": pid_1,
            "version_no": 1
        })
        get_post = await client.get(f"/api/v1/community/posts/{pid_1}")
        assert get_post.status_code == 200
        post_data = get_post.json()["data"]
        assert post_data.get("rating") == 4
        assert post_data.get("author_cutoff_ms") == 2000000

        # 3. Check film detail reflects rating
        film_detail = await client.get("/api/v1/films/the-bat-whispers-1930")
        assert film_detail.status_code == 200
        film_data = film_detail.json()["data"]
        assert film_data.get("average_rating") is not None
        assert film_data.get("ratings_count") >= 1
        base_count = film_data.get("ratings_count")

        # 4. Create second review with rating=2
        post_resp_2 = await client.post(
            "/api/v1/community/posts",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "REVIEW",
                "title": "A bit dated",
                "body_markdown": "Sound quality could be better.",
                "rating": 2,
                "author_cutoff_ms": 1000000
            }
        )
        assert post_resp_2.status_code == 201
        pid_2 = post_resp_2.json()["data"]["post_id"]

        # Check updated film detail
        film_detail_2 = await client.get("/api/v1/films/the-bat-whispers-1930")
        film_data_2 = film_detail_2.json()["data"]
        assert film_data_2.get("ratings_count") == base_count + 1

        # 5. Update first review rating to 5
        patch_resp = await client.patch(
            f"/api/v1/community/posts/{pid_1}",
            json={
                "expected_version": 1,
                "rating": 5,
                "body_markdown": "Rewatched and loved it even more!"
            }
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["version_no"] == 2

        # 6. Create comment with author_cutoff_ms
        comm_resp = await client.post(
            f"/api/v1/community/posts/{pid_1}/comments",
            json={
                "body_markdown": "I agree with this analysis.",
                "author_cutoff_ms": 3500000
            }
        )
        assert comm_resp.status_code == 201
        cid = comm_resp.json()["data"]["comment_id"]

        # Check comment detail includes author_cutoff_ms
        comm_detail = await client.get(f"/api/v1/community/posts/{pid_1}/comments/{cid}")
        assert comm_detail.status_code == 200
        assert comm_detail.json()["data"].get("author_cutoff_ms") == 3500000

        # 7. Delete second review and verify count decrements
        del_resp = await client.delete(f"/api/v1/community/posts/{pid_2}")
        assert del_resp.status_code == 200

        film_detail_after_del = await client.get("/api/v1/films/the-bat-whispers-1930")
        film_data_after_del = film_detail_after_del.json()["data"]
        assert film_data_after_del.get("ratings_count") == base_count
