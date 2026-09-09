"""
Reframe V7 Audience Lab E2E Flow Tests
Tests the full HTTP lifecycle of Audience Lab and Magazine endpoints with authentication and CSRF.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User, Profile
from src.reframe.identity.auth import create_session_token, generate_csrf_token
from src.reframe.shared.config import settings
from src.reframe.jobs.worker import DurableWorker
from src.reframe.jobs.service import job_service



@pytest.mark.asyncio
async def test_audience_lab_e2e_flow(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_AUDIENCE_LAB", True)
    monkeypatch.setattr(settings, "ENABLE_SYNTHETIC_MAGAZINE", True)
    monkeypatch.setattr(settings, "ENABLE_SYNTHETIC_DEMO_CONTENT", True)

    # 1. Create an active Admin user in the database
    admin_user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        admin_user = User(
            id=admin_user_id,
            email_normalized=f"admin_test_{admin_user_id.hex[:8]}@reframe.cinematics",
            status="ACTIVE",
            role="ADMIN",
            account_origin="HUMAN",
        )
        db.add(admin_user)
        admin_prof = Profile(
            user_id=admin_user_id,
            display_name="Audience Lab Admin",
            locale="en",
            fan_depth="DEEP_ANALYST",
        )
        db.add(admin_prof)
        await db.commit()

    admin_token = create_session_token(
        user_id=admin_user_id,
        role="ADMIN",
    )
    csrf_token = generate_csrf_token(admin_token)

    headers = {
        "X-CSRF-Token": csrf_token,
        "Idempotency-Key": f"test_idemp_{uuid.uuid4().hex[:8]}"
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, admin_token)

        # 1. Get Personas Summary
        res = await client.get("/api/v1/admin/audience-lab/personas/summary")
        assert res.status_code == 200, res.text
        summary_data = res.json()
        assert summary_data["dataset_id"] == "nvidia/Nemotron-Personas-USA"
        assert summary_data["license"] == "CC BY 4.0"

        # 2. Create Simulation Run (Async 202)
        run_payload = {
            "mode": "CI",
            "unique_source_personas": 100,
            "variants": ["QUICK_VALUE", "CURRENT_BASELINE"],
            "replications": 1,
            "seed": 42,
        }
        res = await client.post(
            "/api/v1/admin/audience-lab/runs",
            json=run_payload,
            headers=headers,
        )
        assert res.status_code == 202, res.text
        run_data = res.json()
        run_id = uuid.UUID(run_data["run_id"])
        assert run_data["status"] == "QUEUED"

        # Execute durable worker on the queued run
        from sqlalchemy import select
        from src.reframe.jobs.models import AnalysisRun
        worker = DurableWorker()
        async with AsyncSessionLocal() as db:
            res_run = await db.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
            run_obj = res_run.scalar_one_or_none()
            assert run_obj is not None
            await worker.execute_run(db, run_obj)



        # Verify run status is now COMPLETED
        res = await client.get(f"/api/v1/admin/audience-lab/runs/{run_id}")
        assert res.status_code == 200
        completed_run = res.json()
        assert completed_run["status"] == "COMPLETED"

        # 3. Get Funnel
        res = await client.get(f"/api/v1/admin/audience-lab/runs/{run_id}/funnel")
        assert res.status_code == 200
        funnel_data = res.json()
        assert "aggregate_funnel" in funnel_data

        # 4. Get Bottlenecks
        res = await client.get(f"/api/v1/admin/audience-lab/runs/{run_id}/bottlenecks")
        assert res.status_code == 200
        bottlenecks_data = res.json()
        assert "bottlenecks" in bottlenecks_data

        # 5. Get Cohorts
        res = await client.get(f"/api/v1/admin/audience-lab/runs/{run_id}/cohorts")
        assert res.status_code == 200
        cohorts_data = res.json()
        assert "balanced_eval_cohorts" in cohorts_data

        # 6. Get Sensitivity
        res = await client.get(f"/api/v1/admin/audience-lab/runs/{run_id}/sensitivity")
        assert res.status_code == 200
        sensitivity_data = res.json()
        assert "dominant_assumptions" in sensitivity_data

        # 7. List Magazine Articles Before Seeding (Strictly Empty)
        res = await client.get("/api/v1/magazine")
        assert res.status_code == 200
        mag_data_empty = res.json()
        assert mag_data_empty["total"] == 0

        # 8. Seed Content via Run
        seed_headers = {
            "X-CSRF-Token": csrf_token,
            "Idempotency-Key": f"seed_idemp_{uuid.uuid4().hex[:8]}"
        }
        res = await client.post(
            f"/api/v1/admin/audience-lab/runs/{run_id}/seed-content",
            json={
                "posts_count": 2,
                "comments_count": 5,
                "counterclaims_count": 2,
                "reactions_count": 10,
                "enable_magazine": True,
            },
            headers=seed_headers,
        )
        assert res.status_code == 200
        seed_data = res.json()
        assert seed_data["status"] == "SUCCESS"
        assert seed_data["seeded_counts"]["magazine_articles_seeded"] >= 20

        # 9. List Magazine Articles After Seeding (Seeded Articles Present)
        res = await client.get("/api/v1/magazine")
        assert res.status_code == 200
        mag_data = res.json()
        assert mag_data["total"] >= 20

        # 10. Get Magazine Article Detail
        first_art_id = mag_data["articles"][0]["article_id"]
        res = await client.get(f"/api/v1/magazine/{first_art_id}")
        assert res.status_code == 200
        art_detail = res.json()
        assert "title" in art_detail
        assert art_detail["is_synthetic"] is True
        assert "body_sections" in art_detail

        # 11. Calculate Demand Scenario strictly referencing the completed run
        res = await client.post(
            "/api/v1/admin/audience-lab/demand-scenario",
            json={
                "simulation_run_id": str(run_id),
                "monthly_visitors": 50000,
            },
            headers=headers,
        )
        assert res.status_code == 200
        demand_res = res.json()
        assert demand_res["forecast_class"] == "ASSUMPTION_BASED_DIRECTIONAL"
        assert demand_res["real_user_forecast"] is False
        assert demand_res["source_run_id"] == str(run_id)

        # 12. Purge Content
        purge_headers = {
            "X-CSRF-Token": csrf_token,
        }
        res = await client.post(
            "/api/v1/admin/audience-lab/purge-content",
            json={"confirm_delete_synthetic_only": True},
            headers=purge_headers,
        )
        assert res.status_code == 200
        purge_data = res.json()
        assert purge_data["status"] == "PURGED"
        assert purge_data["summary"]["synthetic_users_deleted"] >= 1

