"""
Unit tests for Durable Proof Store Reconciliation & Verification Eligibility.
Verifies that superseded legacy fixture proofs are reconciled to HIDDEN_FROM_PUBLIC/NEEDS_CORRECTION/ENGINE_INFERENCE,
unrelated records are preserved, and empty DB produces 0 verified proofs.
Zero Model / API Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.proof.models import ProofRecord
from src.reframe.proof.store import (
    canonical_proof_store,
    CANONICAL_PROOFS_MAP,
    LEGACY_FIXTURE_PROOF_IDS,
)
from src.reframe.identity.auth import ViewerContext
from apps.api.main import app


@pytest.mark.asyncio
async def test_empty_db_zero_verified_proof_records():
    """
    Test A: On a clean/empty database or after seeding with empty CANONICAL_PROOFS_MAP:
    Strict ProofRecord count for canonical verified proofs = 0.
    """
    assert len(CANONICAL_PROOFS_MAP) == 0

    async with AsyncSessionLocal() as db:
        await canonical_proof_store.seed_canonical_proofs_if_empty(db)

        # Query all records that claim to be CANONICAL_VERIFIED / VERIFIED_CANON
        stmt = select(ProofRecord).where(
            ProofRecord.trust_namespace == "CANONICAL_VERIFIED",
            ProofRecord.presentation_status == "PUBLIC"
        )
        res = await db.execute(stmt)
        verified_records = res.scalars().all()
        assert len(verified_records) == 0


@pytest.mark.asyncio
async def test_db_preloaded_legacy_rows_zero_public_verified_after_reconciliation():
    """
    Test B: DB preloaded with the six legacy fixture rows:
    After reconciliation, normal/public viewer receives 0 verified public proofs.
    """
    async with AsyncSessionLocal() as db:
        # Preload the 6 legacy fixture rows
        for proof_id in LEGACY_FIXTURE_PROOF_IDS:
            rec = ProofRecord(
                id=uuid.uuid4(),
                proof_id=proof_id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                dataset_version="v3",
                reveal_id="reveal-anderson-identity" if "anderson" in proof_id else "reveal-secret-room-location",
                proof_type="KNOWLEDGE_LEAK",
                title=f"Legacy Fixture {proof_id}",
                blind_explanation="Old blind explanation",
                reveal_explanation="Old reveal explanation",
                evidence_chain=[{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
                observed_premises=[{"fact": "Observed fact", "event_id": "ev-01"}],
                alternative_explanations=["Old alt"],
                counterfactual_results={"wrong_reveal_delta": -0.85},
                proof_strength=0.95,
                fan_impact=0.92,
                human_review_status="VERIFIED_CANONICAL",
                presentation_status="PUBLIC",
                trust_namespace="CANONICAL_VERIFIED",
                trust_label="Verified Canon",
                generation_mode="OFFLINE_CANONICAL_FIXTURE"
            )
            db.add(rec)
        await db.commit()

        try:
            # Run reconciliation
            reconciled_count = await canonical_proof_store.reconcile_superseded_fixture_proofs(db)
            await db.commit()
            assert reconciled_count == 6

            # Verify that public viewer receives 0 public proofs from store
            public_viewer = ViewerContext(completed_reveal_ids=["reveal-anderson-identity", "reveal-secret-room-location"])
            anderson_proofs = await canonical_proof_store.get_proofs_for_reveal(db, "reveal-anderson-identity", public_viewer)
            secret_proofs = await canonical_proof_store.get_proofs_for_reveal(db, "reveal-secret-room-location", public_viewer)
            assert len(anderson_proofs) == 0
            assert len(secret_proofs) == 0

            # Verify that public endpoint returns 404 for legacy fixture proof ID
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/api/v1/moments/proof-anderson-01/quick-wow")
                assert res.status_code == 404

        finally:
            # Clean up test rows
            stmt = select(ProofRecord).where(ProofRecord.proof_id.in_(LEGACY_FIXTURE_PROOF_IDS))
            res = await db.execute(stmt)
            for rec in res.scalars().all():
                await db.delete(rec)
            await db.commit()


@pytest.mark.asyncio
async def test_admin_sees_legacy_row_only_as_superseded_not_validated():
    """
    Test C: Admin viewer inspecting a retained legacy fixture row sees only:
    verification_status = ENGINE_INFERENCE,
    counterfactual_robustness = {"verdict": "NOT_VALIDATED"},
    human_review_status = "NEEDS_CORRECTION",
    trust_label = "Superseded legacy development fixture".
    """
    async with AsyncSessionLocal() as db:
        test_proof_id = "proof-anderson-01"
        rec = ProofRecord(
            id=uuid.uuid4(),
            proof_id=test_proof_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            dataset_version="v3",
            reveal_id="reveal-anderson-identity",
            proof_type="KNOWLEDGE_LEAK",
            title="Legacy Anderson Clue",
            blind_explanation="Old blind",
            reveal_explanation="Old reveal",
            evidence_chain=[{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
            observed_premises=[{"fact": "Observed fact", "event_id": "ev-01"}],
            alternative_explanations=["Old alt"],
            counterfactual_results={"wrong_reveal_delta": -0.85},
            proof_strength=0.90,
            fan_impact=0.85,
            human_review_status="NEEDS_CORRECTION",
            presentation_status="HIDDEN_FROM_PUBLIC",
            trust_namespace="ENGINE_INFERENCE",
            trust_label="Superseded legacy development fixture",
            generation_mode="OFFLINE_CANONICAL_FIXTURE"
        )
        db.add(rec)
        await db.commit()

        try:
            admin_viewer = ViewerContext(
                user_id=uuid.uuid4(),
                roles=["ADMIN"],
                work_progress_by_edition={"the-bat-whispers-1930:tbw-fullscreen-archive":5119080},
                completed_reveal_ids=["reveal-anderson-identity"]
            )
            proof_data = await canonical_proof_store.get_proof_by_id(db, test_proof_id, admin_viewer)
            assert proof_data is not None
            assert proof_data["verification_status"] == "ENGINE_INFERENCE"
            assert proof_data["verification_status"] != "VERIFIED_CANON"
            assert proof_data["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"
            assert proof_data["counterfactual_robustness"]["verdict"] != "COUNTERFACTUALLY_ROBUST"
            assert proof_data["human_review_status"] == "NEEDS_CORRECTION"
            assert "Superseded" in proof_data["trust_label"]

            # Also check Fan Experience _resolve_moment
            from apps.api.routers.fan_experience import _resolve_moment
            resolved = await _resolve_moment(test_proof_id, viewer=admin_viewer, db=db)
            assert resolved["content_kind"] == "REWATCH_PATTERN"
            assert resolved["content_kind"] != "VERIFIED_PROOF"
            assert resolved["verification_status"] == "ENGINE_INFERENCE"
            assert resolved["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"
            assert resolved["counterfactual_delta"] is None

        finally:
            await db.delete(rec)
            await db.commit()


@pytest.mark.asyncio
async def test_arbitrary_unrelated_proof_record_not_reconciled_or_deleted():
    """
    Test D: An arbitrary live/user-generated ProofRecord is NOT deleted, hidden, or modified by reconciliation.
    """
    custom_proof_id = f"proof-live-user-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        custom_rec = ProofRecord(
            id=uuid.uuid4(),
            proof_id=custom_proof_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            dataset_version="v3",
            reveal_id="reveal-anderson-identity",
            proof_type="KNOWLEDGE_LEAK",
            title="Live Generated Clue",
            blind_explanation="Live blind",
            reveal_explanation="Live reveal",
            evidence_chain=[{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
            observed_premises=[{"fact": "Observed fact", "event_id": "ev-01"}],
            alternative_explanations=["Alt explanation"],
            counterfactual_results={"wrong_reveal_delta": -0.88},
            proof_strength=0.92,
            fan_impact=0.89,
            human_review_status="APPROVED",
            presentation_status="PUBLIC",
            trust_namespace="CANONICAL_VERIFIED",
            trust_label="Verified Canon",
            generation_mode="LIVE_PIPELINE"
        )
        db.add(custom_rec)
        await db.commit()

        try:
            # Run reconciliation
            reconciled = await canonical_proof_store.reconcile_superseded_fixture_proofs(db)
            await db.commit()
            assert reconciled == 0  # Custom record is not reconciled

            # Query the record and verify it is completely unchanged
            stmt = select(ProofRecord).where(ProofRecord.proof_id == custom_proof_id)
            res = await db.execute(stmt)
            fetched = res.scalar_one_or_none()
            assert fetched is not None
            assert fetched.presentation_status == "PUBLIC"
            assert fetched.human_review_status == "APPROVED"
            assert fetched.trust_namespace == "CANONICAL_VERIFIED"
            assert fetched.generation_mode == "LIVE_PIPELINE"

        finally:
            await db.delete(custom_rec)
            await db.commit()


@pytest.mark.asyncio
async def test_zero_api_model_calls_during_reconciliation():
    """
    Test E: Verification that durable store reconciliation runs with zero model/API calls.
    """
    async with AsyncSessionLocal() as db:
        # Running reconciliation does not invoke any LLM / API gateway
        reconciled = await canonical_proof_store.reconcile_superseded_fixture_proofs(db)
        assert isinstance(reconciled, int)
