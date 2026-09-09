"""Approved product behavior against isolated test DB; no paid calls or live writes."""
import base64
import io
import uuid
import asyncio

from httpx import AsyncClient, ASGITransport
from PIL import Image
from apps.api.main import app

FILM = "the-bat-whispers-1930"
POSTS = "/api/v1/community/posts"


async def login(client):
    result = await client.post("/api/v1/auth/dev-login", json={
        "email": f"engagement-{uuid.uuid4().hex}@example.test", "display_name": "Test Viewer"})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["data"]["csrf_token"]


def review_payload():
    return {"work_id": FILM, "edition_id": "tbw-fullscreen-archive", "content_type": "REVIEW",
            "rating": 4, "title": "My review", "body_markdown": "A thoughtful film.", "contains_spoilers": True}


async def test_review_uniqueness_retry_and_owner_permissions():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner, AsyncClient(transport=transport, base_url="http://test") as other:
        denied = await owner.post(POSTS, json=review_payload())
        assert denied.status_code == 401
        await login(owner)
        await login(other)
        payload = review_payload()
        missing = await owner.post(POSTS, json={**payload, "rating": None})
        assert missing.status_code == 422
        blank = await owner.post(POSTS, json={**payload, "body_markdown": "  "})
        assert blank.status_code == 422
        first = await owner.post(POSTS, json=payload, headers={"Idempotency-Key": "review-retry"})
        assert first.status_code == 201, first.text
        post_id = first.json()["data"]["post_id"]
        replay = await owner.post(POSTS, json=payload, headers={"Idempotency-Key": "review-retry"})
        assert replay.json()["data"]["post_id"] == post_id
        duplicate = await owner.post(POSTS, json=payload, headers={"Idempotency-Key": "another-review"})
        assert duplicate.status_code == 409
        detail = await owner.get(f"{POSTS}/{post_id}")
        assert detail.json()["data"]["contains_spoilers"] is True
        for method, body in (("PATCH", {"expected_version": 1, "body_markdown": "Someone else's edit"}), ("DELETE", None)):
            response = await other.request(method, f"{POSTS}/{post_id}", json=body)
            assert response.status_code == 403
        mine = await owner.get("/api/v1/me/reviews")
        assert [row["post_id"] for row in mine.json()["data"]] == [post_id]
        assert (await other.get("/api/v1/me/reviews")).json()["data"] == []
        assert (await owner.delete(f"{POSTS}/{post_id}")).status_code == 200
        recreated = await owner.post(POSTS, json=payload, headers={"Idempotency-Key": "review-after-delete"})
        assert recreated.status_code == 201, recreated.text


async def test_comment_retry_original_text_and_deleted_parent():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner, AsyncClient(transport=transport, base_url="http://test") as guest:
        await login(owner)
        post = await owner.post(POSTS, json=review_payload())
        post_id = post.json()["data"]["post_id"]
        url = f"{POSTS}/{post_id}/comments"
        original = "  I liked A & B, not <script>alert(1)</script>.\n"
        parent = await owner.post(url, json={"body_markdown": original}, headers={"Idempotency-Key": "parent"})
        assert parent.status_code == 201, parent.text
        parent_id = parent.json()["data"]["comment_id"]
        assert parent.json()["data"]["body_markdown"] == original
        replay = await owner.post(url, json={"body_markdown": original}, headers={"Idempotency-Key": "parent"})
        assert replay.json()["data"]["comment_id"] == parent_id
        reply = await owner.post(url, json={"body_markdown": "Reply stays here", "parent_comment_id": parent_id, "contains_spoilers": True})
        assert reply.status_code == 201
        reply_id = reply.json()["data"]["comment_id"]
        deleted = await owner.delete(f"{url}/{parent_id}")
        assert deleted.status_code == 200
        public = (await guest.get(url)).json()["data"]
        tombstone = next(row for row in public if row["comment_id"] == parent_id)
        assert tombstone["body_markdown"] == "This comment has been deleted."
        assert tombstone["author_id"] is None
        protected_reply = next(row for row in public if row["comment_id"] == reply_id)
        assert protected_reply["is_spoiler_masked"] is True
        own_reply = await owner.get(f"{url}/{reply_id}")
        assert own_reply.status_code == 200
        assert own_reply.json()["data"]["body_markdown"] == "Reply stays here"
        edited = await owner.patch(f"{url}/{reply_id}", json={"expected_version": 1, "body_markdown": "  Edited & unchanged\n", "contains_spoilers": False})
        assert edited.status_code == 200
        assert (await owner.get(f"{url}/{reply_id}")).json()["data"]["body_markdown"] == "  Edited & unchanged\n"
        stale = await owner.patch(f"{url}/{reply_id}", json={"expected_version": 1, "body_markdown": "Stale update"})
        assert stale.status_code == 409


async def test_concurrent_review_creation_and_legacy_rating_edit_cannot_duplicate():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await login(owner)
        requests = [owner.post(POSTS, json=review_payload(), headers={"Idempotency-Key": f"parallel-{i}"}) for i in range(2)]
        results = await asyncio.gather(*requests)
        assert sorted(result.status_code for result in results) == [201, 409]
        legacy = await owner.post(POSTS, json={**review_payload(), "content_type": "FAN_THEORY", "rating": None})
        assert legacy.status_code == 201, legacy.text
        post_id = legacy.json()["data"]["post_id"]
        duplicate_edit = await owner.patch(f"{POSTS}/{post_id}", json={"expected_version": 1, "rating": 5})
        assert duplicate_edit.status_code == 409
        assert (await owner.get("/api/v1/me/reviews")).json()["meta"]["total"] == 1


async def test_proof_comment_retries_and_spoiler_flag_on_real_route(monkeypatch):
    from src.reframe.proof.store import canonical_proof_store
    from unittest.mock import AsyncMock
    proof_id = f"approved-proof-{uuid.uuid4()}"
    monkeypatch.setattr(canonical_proof_store, "get_proof_by_id", AsyncMock(return_value={"proof_id": proof_id, "title": "Test interpretation", "work_id": FILM, "edition_id": "tbw-fullscreen-archive"}))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as owner:
        await login(owner)
        url = f"/api/v1/proofs/{proof_id}/comments"
        body = {"body_markdown": "  Original words & punctuation.\n", "contains_spoilers": True}
        first = await owner.post(url, json=body, headers={"Idempotency-Key": "proof-retry"})
        assert first.status_code == 201, first.text
        second = await owner.post(url, json=body, headers={"Idempotency-Key": "proof-retry"})
        assert first.json() == second.json()
        assert first.json()["data"]["body_markdown"] == body["body_markdown"]
        changed = await owner.post(url, json={**body, "body_markdown": "Different"}, headers={"Idempotency-Key": "proof-retry"})
        assert changed.status_code == 409
        assert len((await owner.get(url)).json()["data"]) == 1


async def test_wishlist_isolated_idempotent_and_profile_photo_validation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as owner, AsyncClient(transport=transport, base_url="http://test") as other:
        assert (await owner.get("/api/v1/me/wishlist")).status_code == 401
        await login(owner)
        await login(other)
        url = f"/api/v1/me/wishlist/{FILM}"
        for _ in range(2):
            assert (await owner.put(url, json={"saved": True})).status_code == 200
        assert (await owner.get("/api/v1/me/wishlist")).json()["meta"]["total"] == 1
        assert (await other.get("/api/v1/me/wishlist")).json()["data"] == []
        assert (await owner.put(url, json={"saved": False})).json()["data"]["saved"] is False
        assert (await owner.put(url, json={"saved": True})).json()["data"]["saved"] is True
        assert (await owner.patch("/api/v1/profiles/me", json={"display_name": "  "})).status_code == 422
        assert (await owner.patch("/api/v1/profiles/me", json={"display_name": "Test", "role": "ADMIN"})).status_code == 422
        assert (await owner.patch("/api/v1/profiles/me", json={"display_name": "Test", "photo_data": "data:image/svg+xml;base64,PHN2Zy8+"})).status_code == 422
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "purple").save(buffer, format="PNG")
        photo = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
        saved = await owner.patch("/api/v1/profiles/me", json={"display_name": "My nickname", "photo_data": photo})
        assert saved.status_code == 200, saved.text
        avatar = await owner.get(saved.json()["data"]["avatar_url"])
        assert avatar.headers["content-type"] == "image/png"
        assert avatar.headers["x-content-type-options"] == "nosniff"
        profile = (await owner.get("/api/v1/profiles/me")).json()["data"]
        assert profile["display_name"] == "My nickname"
        assert profile["role"] == "USER"
