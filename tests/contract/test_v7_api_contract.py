"""
Reframe V7 API Contract & Health Tests
"""
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings



@pytest.mark.asyncio
async def test_live_and_ready_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /live
        res_live = await client.get("/live")
        assert res_live.status_code == 200
        assert res_live.json()["status"] == "ALIVE"

        # 2. /ready
        res_ready = await client.get("/ready")
        assert res_ready.status_code == 200
        data = res_ready.json()["data"]
        assert "postgres" in data
        assert "runtime_db_readonly" in data
        assert data["runtime_db_readonly"] is True


@pytest.mark.asyncio
async def test_catalog_films_and_reveals():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /api/v1/films
        res_films = await client.get("/api/v1/films")
        assert res_films.status_code == 200
        films = res_films.json()["data"]
        assert len(films) == 1
        assert films[0]["movie_id"] == "the-bat-whispers-1930"

        # 2. /api/v1/films/the-bat-whispers-1930
        res_detail = await client.get("/api/v1/films/the-bat-whispers-1930")
        assert res_detail.status_code == 200
        film_detail = res_detail.json()["data"]
        assert film_detail["scenes_count"] == 43
        assert film_detail["reveals_count"] == 4

        # 3. /api/v1/films/the-bat-whispers-1930/reveals (Guest / unauthenticated)
        res_reveals = await client.get("/api/v1/films/the-bat-whispers-1930/reveals")
        assert res_reveals.status_code == 200
        reveals = res_reveals.json()["data"]
        assert len(reveals) == 4
        # Since guest hasn't watched, reveals should be LOCKED with safe titles
        anderson_rev = next(r for r in reveals if r["reveal_id"] == "reveal-anderson-identity")
        assert anderson_rev["visibility"] == "LOCKED"
        assert anderson_rev["title"] == "The true identity of the master criminal 'The Bat'"


@pytest.mark.asyncio
async def test_auth_dev_login_and_me_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial /me as guest
        res_guest = await client.get("/api/v1/me")
        assert res_guest.status_code == 200
        assert res_guest.json()["data"]["role"] == "GUEST"

        # 2. Login via dev provider
        login_res = await client.post("/api/v1/auth/dev-login", json={
            "email": "investigator@reframe.dev",
            "display_name": "Senior Investigator"
        })
        assert login_res.status_code == 200
        session_token = login_res.cookies.get(settings.SESSION_COOKIE_NAME)
        csrf = login_res.json()["data"]["csrf_token"]
        assert session_token is not None
        client.cookies.set(settings.SESSION_COOKIE_NAME, session_token)

        # 3. Authenticated /me
        res_auth = await client.get("/api/v1/me")
        assert res_auth.status_code == 200
        user_data = res_auth.json()["data"]
        assert user_data["display_name"] == "Senior Investigator"
        assert user_data["role"] == "USER"

        # 4. Update watch progress (mark complete)
        prog_res = await client.put(
            "/api/v1/me/watch-progress/the-bat-whispers-1930",
            headers={"X-CSRF-Token": csrf},
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "COMPLETED",
                "progress_ms": 5040000,
                "completed_reveal_ids": ["reveal-anderson-identity"]
            }
        )
        assert prog_res.status_code == 200

        # 5. Now check reveals as completed viewer -> reveal is VISIBLE with original title
        rev_auth = await client.get("/api/v1/films/the-bat-whispers-1930/reveals")
        assert rev_auth.status_code == 200

        reveals = rev_auth.json()["data"]
        anderson_rev = next(r for r in reveals if r["reveal_id"] == "reveal-anderson-identity")
        assert anderson_rev["visibility"] == "VISIBLE"
        assert "Unmasked as 'The Bat'" in anderson_rev["title"]


@pytest.mark.asyncio
async def test_proof_and_moment_api_contract():
    """Verify ProofApi contract routes against /api/v1/reveals/{id}/proofs and /api/v1/proofs/{id}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get reveal proofs
        proofs_res = await client.get("/api/v1/reveals/reveal-anderson-identity/proofs")
        assert proofs_res.status_code == 200
        proofs = proofs_res.json()["data"]
        assert isinstance(proofs, list)

        # Check proof detail if proofs exist or 404 on nonexistent
        not_found_res = await client.get("/api/v1/proofs/nonexistent-proof-999")
        assert not_found_res.status_code == 404
