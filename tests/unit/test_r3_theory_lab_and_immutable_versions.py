"""
Unit Tests for R3-07 & R3-08: Theory Lab Semantic Analysis and Immutable Versioning
Verifies immutable version increments and proves Theory A and Theory B produce genuinely different outputs.
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.community.models import Post, PostVersion
from src.reframe.narrative.theory_engine import theory_engine, TheoryValidationResult
from src.reframe.jobs.worker import DurableWorker


def test_theory_engine_divergent_outputs_on_same_reveal():
    """
    Verify Theory A (grounded in fireplace mechanism) and Theory B (astronaut gardener)
    produce completely distinct scores and verdicts for the same reveal.
    """
    # Theory A: Grounded in canon clues
    input_a = {
        "theory_id": "theory-a",
        "post_version_id": "v1",
        "theory_text": "Detective stands on stepladder to examine the painting above the fireplace and touches mechanism located on mantel.",
        "target_reveal_id": "reveal-secret-room-location"
    }
    result_a = theory_engine.validate_theory(input_a)
    assert isinstance(result_a, TheoryValidationResult)
    assert result_a.grounding_score >= 0.50
    assert result_a.validation_verdict == "RELATED_EVIDENCE"
    assert result_a.validation_mode == "LOCAL_KEYWORD_RETRIEVAL"
    assert result_a.counterfactual_results == {"status": "NOT_RUN"}
    assert result_a.uncertainty is None
    assert len(result_a.supporting_evidence) >= 1

    # Theory B: Completely ungrounded / fabricated
    input_b = {
        "theory_id": "theory-b",
        "post_version_id": "v1",
        "theory_text": "The gardener is secretly an astronaut orbiting the moon with rocket propulsion.",
        "target_reveal_id": "reveal-secret-room-location"
    }
    result_b = theory_engine.validate_theory(input_b)
    assert isinstance(result_b, TheoryValidationResult)
    assert result_b.grounding_score < 0.20
    assert result_b.validation_verdict == "NO_MATCH"
    assert len(result_b.supporting_evidence) == 0

    # Invariant: Must not be identical
    assert result_a.grounding_score != result_b.grounding_score
    assert result_a.validation_verdict != result_b.validation_verdict


@pytest.mark.asyncio
async def test_immutable_theory_versioning_and_run_detail():
    """Verify editing a theory creates PostVersion v2 without mutating v1, and run detail reads real result."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Authenticate
        auth_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"role": "USER", "email": "theory_fan@reframe.dev"}
        )
        assert auth_resp.status_code == 200
        data = auth_resp.json()["data"]
        csrf_token = data["csrf_token"]
        session_cookie = auth_resp.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
        headers = {
            "X-CSRF-Token": csrf_token
        }
        progress = await client.put("/api/v1/me/watch-progress/the-bat-whispers-1930", json={
            "edition_id": "tbw-fullscreen-archive", "state": "COMPLETED", "progress_ms": 5040000,
            "completed_reveal_ids": ["reveal-secret-room-location"]}, headers=headers)
        assert progress.status_code == 200

        # 1. Create Theory (v1)
        create_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-secret-room-location",
                "title": "Fireplace Secret Wall Theory",
                "hypothesis_explanation": "The fireplace mantel contains a mechanical trigger operated by characters.",
            },
            headers=headers
        )
        assert create_resp.status_code == 201
        theory_id = create_resp.json()["data"]["theory_id"]

        # Inspect v1 in DB
        async with AsyncSessionLocal() as db:
            post_stmt = select(Post).where(Post.id == uuid.UUID(theory_id))
            post = (await db.execute(post_stmt)).scalar_one()
            v1_id = post.current_version_id

            v1_stmt = select(PostVersion).where(PostVersion.id == v1_id)
            v1 = (await db.execute(v1_stmt)).scalar_one()
            assert v1.version_no == 1
            v1_text = v1.body_markdown

        # 2. Update Theory (creates v2)
        update_resp = await client.patch(
            f"/api/v1/theories/{theory_id}",
            json={
                "title": "Fireplace Secret Wall Theory Revision",
                "hypothesis_explanation": "The fireplace mantel contains a mechanical trigger and examination above fireplace painting.",
                "change_summary": "Added painting examination detail"
            },
            headers=headers
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["version_no"] == 2

        # Verify DB: v1 remains completely unchanged, post points to v2
        async with AsyncSessionLocal() as db:
            v1_check = (await db.execute(select(PostVersion).where(PostVersion.id == v1_id))).scalar_one()
            assert v1_check.version_no == 1
            assert v1_check.body_markdown == v1_text

            post_check = (await db.execute(select(Post).where(Post.id == uuid.UUID(theory_id)))).scalar_one()
            assert post_check.current_version_id != v1_id

            v2 = (await db.execute(select(PostVersion).where(PostVersion.id == post_check.current_version_id))).scalar_one()
            assert v2.version_no == 2
            assert "painting" in v2.body_markdown

        # 3. Create Theory Run
        run_resp = await client.post(
            "/api/v1/theory-runs",
            json={
                "theory_id": theory_id,
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-secret-room-location"
            },
            headers={**headers, "Idempotency-Key": f"key-theory-{uuid.uuid4().hex}"}
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["data"]["run_id"]

        # Worker executes run
        worker = DurableWorker(worker_id="test-theory-worker")
        for _ in range(5):
            had_work = await worker.run_once()
            if not had_work:
                break

        # 4. Check GET /theory-runs/{id}
        detail_resp = await client.get(
            f"/api/v1/theory-runs/{run_id}",
            headers=headers
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()["data"]
        assert detail["status"] == "COMPLETED"
        assert detail["grounding_score"] >= 0.50
        assert detail["validation_verdict"] == "RELATED_EVIDENCE"
        assert detail["uncertainty"] is None
        assert len(detail["supporting_evidence"]) >= 1
