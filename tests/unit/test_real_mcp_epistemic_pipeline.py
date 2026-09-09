"""
Reframe V7 Real MCP Epistemic Plumbing & Pattern Trust Certification Tests
Validates end-to-end MCP retrieval pipeline against reframe.knowledge_states,
strict LiveKnowledgeEvidence semantics, explicit public availability,
proposition binding, and fan experience pattern trust labels.
Zero Paid Model Calls ($0.00 spend).
"""
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from src.reframe.domain.enums import ExecutionMode
from src.reframe.mcp.program import NarrativeMcpRetrievalProgram
from src.reframe.mcp.adapter import McpEvidenceSeedAdapter
from src.reframe.narrative.bundle import EvidenceBundleBuilder
from src.reframe.narrative.obligations import (
    KnowledgeStateResolver,
    KnowledgeLeakObligation,
    LiveKnowledgeEvidence,
    AvailabilityStatus,
    ProofValidationContext,
    KnowledgeSourceType
)
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.proof.validator import DeterministicProofValidator, proof_validator
from src.reframe.narrative.snapshot_repo import (
    DeepSnapshotRepository,
    SnapshotIntegrityError,
    EXPECTED_DEEP_SNAPSHOT_V1_1_CORPUS_CORRECTIONS_SHA256
)
from src.reframe.proof.store import CANONICAL_PATTERNS_MAP, canonical_proof_store
from src.reframe.identity.auth import ViewerContext
from src.reframe.shared.config import settings


@pytest.mark.asyncio
async def test_end_to_end_mcp_to_resolver_pipeline_zero_snapshot_access():
    """
    Test 1: End-to-end integration test:
    NarrativeMcpRetrievalProgram -> McpEvidenceSeedAdapter -> EvidenceBundleBuilder(LIVE_GOOGLE)
    -> bundle.mcp_knowledge_evidence -> ProofValidationContext -> KnowledgeStateResolver.
    Asserts zero calls to DeepSnapshotRepository.
    """
    program = NarrativeMcpRetrievalProgram()
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    assert reveal is not None

    with patch.object(DeepSnapshotRepository, "get_knowledge_propositions", side_effect=RuntimeError("SNAPSHOT_CALLED_IN_LIVE_MODE")):
        mcp_results, seeds = await program.execute_program(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            cutoff_ms=reveal.timestamp_ms,
            analysis_run_id="test-e2e-mcp-01"
        )

        assert len(mcp_results) == 5
        assert len(seeds) == 5

        # Check Channel 2 result
        kc_res = next(r for r in mcp_results if r.phase == "KNOWLEDGE_CONFLICT")
        assert kc_res.query_text.startswith("SELECT knowledge_id, subject, predicate, object, status, valid_from_ms")
        for row in kc_res.raw_rows:
            assert row["source_table"] == "knowledge_states"

        # Build bundle in LIVE_GOOGLE mode
        bundle = EvidenceBundleBuilder.build_bundle(
            reveal=reveal,
            provided_seeds=seeds,
            execution_mode=ExecutionMode.LIVE_GOOGLE
        )

        assert len(bundle.mcp_knowledge_evidence) > 0
        for r in bundle.mcp_knowledge_evidence:
            assert r["source_table"] == "knowledge_states"

        # Resolve epistemic state in LIVE mode
        live_ctx = ProofValidationContext(
            execution_mode=ExecutionMode.LIVE_GOOGLE,
            evidence_source="LIVE_MCP",
            knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
            answer_assisted=False,
            mcp_evidence=bundle.mcp_knowledge_evidence
        )

        kp = KnowledgeStateResolver.resolve_epistemic_state(
            work_id="the-bat-whispers-1930",
            character="Detective Anderson",
            proposition="Oakdale Manor contains secret rooms and structural hidden passages as evidenced by the house blueprints.",
            cutoff_ms=reveal.timestamp_ms,
            context=live_ctx,
            proposition_id="ks-act2-001"
        )

        assert kp is not None
        assert kp.character_available_from_ms > 0
        # When public_available_from_ms is 0, status in export is INFERRED
        assert kp.availability_status == AvailabilityStatus.INFERRED


def test_generic_events_fail_closed_for_knowledge():
    """
    Test 2: Generic MCP event rows (source_table != knowledge_states) must NOT produce KNOWN status.
    """
    generic_rows = [
        {
            "source_table": "events",
            "event_id": "ev-01",
            "actor": "Detective Anderson",
            "action": "walks into room",
            "timestamp_ms": 2000000,
            "evidence_refs": ["scene-01"]
        }
    ]
    live_ctx = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=generic_rows
    )

    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Secret room exists",
        cutoff_ms=3000000,
        context=live_ctx
    )
    assert kp.availability_status == AvailabilityStatus.UNKNOWN
    assert kp.public_available_from_ms == 0
    assert kp.character_available_from_ms == 0


def test_knowledge_states_without_explicit_public_availability_fails_closed_for_leak():
    """
    Test 3: knowledge_states row with public_available_from_ms == 0 must fail closed for KNOWLEDGE_LEAK.
    """
    typed_rows = [
        {
            "source_table": "knowledge_states",
            "proposition_id": "prop-secret-01",
            "character": "Detective Anderson",
            "normalized_proposition": "Detective Anderson knows the hidden safe combination",
            "availability_ms": 1500000,
            "public_available_from_ms": 0,  # Missing explicit public broadcast
            "access_type": "OBSERVED",
            "evidence_refs": ["scene-02"],
            "confidence": 0.95
        }
    ]
    live_ctx = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=typed_rows
    )

    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson knows the hidden safe combination",
        cutoff_ms=4000000,
        context=live_ctx,
        proposition_id="prop-secret-01"
    )
    assert kp.availability_status == AvailabilityStatus.KNOWN
    assert kp.public_available_from_ms == 0

    # KnowledgeLeakObligation must fail closed
    obl_res = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=kp.public_available_from_ms,
        earliest_character_access_ms=kp.character_available_from_ms,
        evidence_ids=["scene-02"],
        knowledge_proposition=kp
    )
    assert obl_res.is_satisfied is False
    assert "UNKNOWN_EPISTEMIC_AVAILABILITY" in obl_res.broken_rules or "MISSING_TIMESTAMP" in obl_res.broken_rules


def test_inferred_and_discovers_access_types_never_convert_to_known():
    """
    Test 4: INFERRED or DISCOVERS_BY_OPERATION must map to AvailabilityStatus.INFERRED, never KNOWN.
    """
    inferred_rows = [
        {
            "source_table": "knowledge_states",
            "proposition_id": "prop-inferred-01",
            "character": "Detective Anderson",
            "normalized_proposition": "Detective Anderson deduces the killer entered from the roof",
            "availability_ms": 1200000,
            "public_available_from_ms": 3000000,
            "access_type": "INFERRED",
            "evidence_refs": ["scene-03"],
            "confidence": 0.90
        },
        {
            "source_table": "knowledge_states",
            "proposition_id": "prop-discovers-01",
            "character": "Dale Ogden",
            "normalized_proposition": "Dale Ogden operates the fireplace mantel latch",
            "availability_ms": 1400000,
            "public_available_from_ms": 3000000,
            "access_type": "DISCOVERS_BY_OPERATION",
            "evidence_refs": ["scene-04"],
            "confidence": 0.90
        }
    ]
    live_ctx = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=inferred_rows
    )

    kp1 = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson deduces the killer entered from the roof",
        cutoff_ms=4000000,
        context=live_ctx,
        proposition_id="prop-inferred-01"
    )
    assert kp1.availability_status == AvailabilityStatus.INFERRED

    kp2 = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Dale Ogden",
        proposition="Dale Ogden operates the fireplace mantel latch",
        cutoff_ms=4000000,
        context=live_ctx,
        proposition_id="prop-discovers-01"
    )
    assert kp2.availability_status == AvailabilityStatus.INFERRED

    # Both must fail KnowledgeLeakObligation
    obl1 = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=kp1.public_available_from_ms,
        earliest_character_access_ms=kp1.character_available_from_ms,
        evidence_ids=["scene-03"],
        knowledge_proposition=kp1
    )
    assert obl1.is_satisfied is False

    obl2 = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=kp2.public_available_from_ms,
        earliest_character_access_ms=kp2.character_available_from_ms,
        evidence_ids=["scene-04"],
        knowledge_proposition=kp2
    )
    assert obl2.is_satisfied is False


def test_observed_with_explicit_public_and_character_availability_satisfies_leak():
    """
    Test 5: OBSERVED access type + explicit public broadcast + character access before public -> satisfies KNOWLEDGE_LEAK.
    """
    valid_rows = [
        {
            "source_table": "knowledge_states",
            "proposition_id": "prop-known-01",
            "character": "Detective Anderson",
            "normalized_proposition": "Detective Anderson has private unbriefed blueprint of secret room",
            "availability_ms": 1000000,
            "public_available_from_ms": 3500000,
            "access_type": "OBSERVED",
            "evidence_refs": ["scene-tbw-c011"],
            "confidence": 0.95
        }
    ]
    live_ctx = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=valid_rows
    )

    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson has private unbriefed blueprint of secret room",
        cutoff_ms=4000000,
        context=live_ctx,
        proposition_id="prop-known-01"
    )
    assert kp.availability_status == AvailabilityStatus.KNOWN
    assert kp.character_available_from_ms == 1000000
    assert kp.public_available_from_ms == 3500000

    obl = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=kp.public_available_from_ms,
        earliest_character_access_ms=kp.character_available_from_ms,
        evidence_ids=["scene-tbw-c011"],
        knowledge_proposition=kp
    )
    assert obl.is_satisfied is True
    assert obl.score >= 0.90


def test_wrong_proposition_id_fails_closed():
    """
    Test 6: Proposition ID mismatch or missing proposition binding fails closed with UNKNOWN.
    """
    rows = [
        {
            "source_table": "knowledge_states",
            "proposition_id": "prop-known-01",
            "character": "Detective Anderson",
            "normalized_proposition": "Detective Anderson has private unbriefed blueprint of secret room",
            "availability_ms": 1000000,
            "public_available_from_ms": 3500000,
            "access_type": "OBSERVED",
            "evidence_refs": ["scene-tbw-c011"],
            "confidence": 0.95
        }
    ]
    live_ctx = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=rows
    )

    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Unrelated proposition about a stolen watch",
        cutoff_ms=4000000,
        context=live_ctx,
        proposition_id="prop-wrong-99"
    )
    assert kp.availability_status == AvailabilityStatus.UNKNOWN


@pytest.mark.asyncio
async def test_fan_experience_rewatch_pattern_404_for_public_and_trust_labels_for_admin():
    """
    Test 7 & 8:
    - Public/guest request for HIDDEN_FROM_PUBLIC REWATCH_PATTERN returns 404.
    - Admin request for REWATCH_PATTERN returns proof_badge="Rewatch Pattern",
      verification_status="ENGINE_INFERENCE", counterfactual_robustness={"verdict": "NOT_VALIDATED"}.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        pattern_id = "pattern-anderson-01"

        # 1. Unauthenticated/Guest request -> 404
        res_guest = await client.get(f"/api/v1/moments/{pattern_id}/quick-wow")
        assert res_guest.status_code == 404

        res_guest_trust = await client.get(f"/api/v1/moments/{pattern_id}/trust-label")
        assert res_guest_trust.status_code == 404

        # 2. Normal authenticated fan (non-admin) -> 404
        fan_login = await client.post("/api/v1/auth/dev-login", json={"email": "fan@reframe.dev"})
        fan_token = fan_login.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, fan_token)

        res_fan = await client.get(f"/api/v1/moments/{pattern_id}/quick-wow")
        assert res_fan.status_code == 404

        # 3. Admin viewer -> 200 with truthful non-normative labels
        import uuid
        from src.reframe.identity.models import User
        from src.reframe.identity.auth import create_session_token
        from src.reframe.shared.database import AsyncSessionLocal

        admin_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            admin_user = User(id=admin_id, email_normalized="admin_test_epistemic@reframe.dev", role="ADMIN", status="ACTIVE")
            db.add(admin_user)
            await db.commit()

        admin_token = create_session_token(admin_id, "ADMIN")
        client.cookies.set(settings.SESSION_COOKIE_NAME, admin_token)

        res_admin_quick = await client.get(f"/api/v1/moments/{pattern_id}/quick-wow")
        assert res_admin_quick.status_code == 200
        data_quick = res_admin_quick.json()["data"]
        assert data_quick["proof_badge"] == "Rewatch Pattern"
        assert "Verified Canon" not in data_quick["proof_badge"]

        res_admin_trust = await client.get(f"/api/v1/moments/{pattern_id}/trust-label")
        assert res_admin_trust.status_code == 200
        data_trust = res_admin_trust.json()["data"]
        assert data_trust["verification_status"] == "ENGINE_INFERENCE"
        assert data_trust["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"


def test_snapshot_release_anchor_integrity():
    """
    Test 9: Snapshot release anchor constant is verified at load time.
    Mismatch raises SnapshotIntegrityError.
    """
    assert EXPECTED_DEEP_SNAPSHOT_V1_1_CORPUS_CORRECTIONS_SHA256 == "6ffa08484bbda4af542911f4987b786fde5057ede950ca563683634fa7cf0b90"

    # DeepSnapshotRepository._verify_phase_a_lock passes on clean data
    base_dir = DeepSnapshotRepository._get_base_dir("deep_snapshot_v1_1")
    assert DeepSnapshotRepository._verify_phase_a_lock(base_dir, "deep_snapshot_v1_1") is True
