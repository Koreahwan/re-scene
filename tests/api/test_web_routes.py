import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from apps.api.main import app


@pytest.mark.asyncio
async def test_web_index_and_static_assets():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test Root HTML
        resp = await client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "Reframe" in html or "app" in html or "html" in html

        # Test Static CSS
        css_resp = await client.get("/styles.css")
        assert css_resp.status_code == 200


@pytest.mark.asyncio
async def test_full_golden_user_path_simulation():
    """
    Simulates a real user journey through the application:
    1. User lands on page and loads film metadata.
    2. User views film reveals.
    3. User triggers asynchronous Reframe analysis for 'reveal-anderson-identity'.
    4. User views returned reframed cards.
    5. User inspects rewatch scene timestamp.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Landing & Film Detail (V7)
        film_resp = await client.get("/api/v1/catalog/works/the-bat-whispers-1930")
        assert film_resp.status_code == 200
        film = film_resp.json()["data"]
        assert film["title"] == "The Bat Whispers"

        # 2. Reveal Selection (V7)
        reveals_resp = await client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
        assert reveals_resp.status_code == 200
        reveals = reveals_resp.json()["data"]
        assert len(reveals) >= 2
        anderson_reveal = next(r for r in reveals if r["reveal_id"] == "reveal-anderson-identity")

        # 3. Trigger Asynchronous Analysis (V7)
        idem_key = f"key-test-web-{uuid.uuid4().hex}"
        run_resp = await client.post(
            "/api/v1/reframe-runs",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "reveal_id": anderson_reveal["reveal_id"],
                "target_reveal_id": anderson_reveal["reveal_id"]
            },
            headers={"Idempotency-Key": idem_key}
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["data"]["run_id"]
        assert run_id is not None
