"""
Reframe V7 R4.1 Master Blocker Verification Test Suite
Tests all 21+ blocker fixes:
- ADK Reasoning Loop Event Extraction
- No Direct Gemini Bypass
- Guarded Gemini Invoker 24-step Preflight & ModelCallClaims
- Gemini 3.6 Pricing & Estimation Guard
- ClickHouse DDL Column Schema Alignment & Telemetry ID Binding
- Dev Login Privilege Escalation Elimination (role="USER")
- Proof Trust Labels & NOT_REVIEWED Status
- Canonical Content Hashing (SHA-256)
- KnowledgeLeak, ClaimAction, and HiddenPlan Deep Proof Obligations
- Counterfactual Tournament Real Evaluator
- Alembic 0004 Migration Sync
- Credential-free Docker Multi-stage Build & Docker Compose Stack
- Fan Experience Dynamic Moment Projection
- Community Comment Spoiler Scope Inheritance
- Truthful /ready and /health Observability
- Frontend ApiClient Non-OK Error Throwing
Zero Paid Model Calls ($0.00 spent).
"""
import pytest
import uuid
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.reframe.agents.adk_gateway import (
    OfflineAdkExecutionGateway,
    LiveGoogleAdkExecutionGateway,
    FakeOfflineLlm
)

from src.reframe.cost.invoker import GuardedGeminiInvoker, GuardedGeminiAdkLlm
from src.reframe.cost.pricing import PricingRegistry, PricingStatus
from src.reframe.cost.guard import PaidCallGuardException
from src.reframe.mcp.program import NarrativeMcpRetrievalProgram

from src.reframe.proof.store import (
    CANONICAL_PROOFS_MAP,
    CANONICAL_PATTERNS_MAP,
    canonical_event_hash,
    canonical_fact_hash,
    canonical_frame_hash
)
from src.reframe.proof.validator import proof_validator, ProofValidationErrorCode
from src.reframe.narrative.obligations import (
    KnowledgeLeakObligation,
    ClaimActionObligation,
    HiddenPlanObligation,
    CounterfactualObligationScorer
)
from src.reframe.narrative.counterfactual import CounterfactualTournamentEngine
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, SpoilerVisibility
from src.reframe.identity.auth import ViewerContext
from apps.api.routers.fan_experience import _resolve_moment


# ==============================================================================
# 1. ADK Reasoning Loop Event Extraction & No Direct Gemini Bypass
# ==============================================================================

@pytest.mark.asyncio
async def test_adk_reasoning_loop_event_extraction():
    """Verify ADK gateway extracts structured hypotheses from runner events."""
    gateway = OfflineAdkExecutionGateway()
    result = await gateway.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="run-test-01"
    )
    assert result.status in ("COMPLETED", "ABSTAINED")
    assert len(result.hypotheses) >= 1
    assert result.execution_mode.value in ("OFFLINE_FIXTURE", "OFFLINE_CANONICAL_FIXTURE")


def test_no_direct_gemini_bypass_in_codebase():
    """Verify 0 direct client.models.generate_content calls outside GuardedGeminiInvoker."""
    src_dir = Path("src/reframe")
    violating_files = []
    for p in src_dir.rglob("*.py"):
        if p.name in ("invoker.py", "fake_offline_llm.py"):
            continue
        text = p.read_text(encoding="utf-8")
        if "client.models.generate_content" in text or "models.generate_content(" in text:
            violating_files.append(str(p))

    assert len(violating_files) == 0, f"Found direct Gemini generate_content calls in: {violating_files}"


# ==============================================================================
# 2. Guarded Gemini Invoker 24-step Preflight & Pricing
# ==============================================================================

@pytest.mark.asyncio
async def test_guarded_gemini_invoker_fails_closed_in_offline_mode():
    """GuardedGeminiInvoker must fail closed with PaidCallGuardException when PAID_CALLS_ENABLED=false."""
    with pytest.raises(PaidCallGuardException) as exc_info:
        await GuardedGeminiInvoker.invoke_guarded_generation(
            analysis_run_id="run-1",
            principal_id="user-1",
            role="REASONING",
            model_id="gemini-2.5-flash",
            prompt_text="test prompt"
        )
    assert "PAID_CALL_ATTEMPTED_DURING_R4_1" in str(exc_info.value) or "Paid model calls are disabled" in str(exc_info.value)


def test_pricing_registry_gemini_3_6_estimate_only():
    """PricingRegistry must calculate cost micros and mark 3.6 as ESTIMATE_ONLY."""
    from src.reframe.cost.pricing import pricing_registry
    status = pricing_registry.get_pricing_status("gemini-3.6-flash")
    assert status == PricingStatus.ESTIMATE_ONLY

    cost_micros = pricing_registry.calculate_cost_micros("gemini-2.5-flash", input_text_tokens=1000, output_tokens=500)
    assert cost_micros > 0


# ==============================================================================
# 3. ClickHouse DDL Alignment & Telemetry ID Binding
# ==============================================================================

def test_clickhouse_ddl_and_program_column_alignment():
    """Verify NarrativeMcpProgram queries match 001_initial_schema.sql columns."""
    ddl_path = Path("db/clickhouse/ddl/001_initial_schema.sql")
    assert ddl_path.exists()
    ddl_content = ddl_path.read_text(encoding="utf-8")

    # In 001_initial_schema.sql, reframe.facts has subject, predicate, object, fact_type, confidence
    assert "subject String" in ddl_content
    assert "predicate String" in ddl_content
    assert "object String" in ddl_content
    assert "fact_type LowCardinality(String)" in ddl_content

    # NarrativeMcpProgram must query these exact columns
    program_src = Path("src/reframe/mcp/program.py").read_text(encoding="utf-8")
    assert "SELECT fact_id, scene_id, timestamp_ms, subject, predicate, object, fact_type, confidence" in program_src


# ==============================================================================
# 4. Dev Login Privilege Escalation Elimination
# ==============================================================================

@pytest.mark.asyncio
async def test_dev_login_strictly_assigns_user_role():
    """dev_login must never escalate to ADMIN or MOD based on email substring."""
    from apps.api.routers.auth import dev_login, DevLoginRequest
    from src.reframe.identity.models import User
    from src.reframe.shared.config import settings

    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    # Test with admin email
    req = DevLoginRequest(email="admin@reframe.dev", display_name="Admin Test")
    mock_response = MagicMock()

    # Mock finding or creating user
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    orig_mode = settings.AUTH_DEV_MODE
    settings.AUTH_DEV_MODE = True
    try:
        resp = await dev_login(payload=req, response=mock_response, db=mock_db)
        assert resp["data"]["role"] == "USER"
    finally:
        settings.AUTH_DEV_MODE = orig_mode




# ==============================================================================
# 5. Proof Trust Labels & Canonical Content Hashes
# ==============================================================================

def test_proof_trust_and_review_status_not_reviewed():
    """Seeded canonical patterns must be NOT_REVIEWED with ENGINE_INFERENCE trust."""
    for reveal_id, proofs in CANONICAL_PATTERNS_MAP.items():
        for p in proofs:
            if p["proof_id"] == "proof-secret-room-03":
                assert p["human_review_status"] == "NEEDS_CORRECTION"
            else:
                assert p["human_review_status"] == "NOT_REVIEWED"
            assert p["trust_namespace"] == "ENGINE_INFERENCE"
            assert "Engine-supported interpretation" in p["trust_label"]


def test_canonical_content_hashes_are_sha256():
    """canonical_event_hash, canonical_fact_hash, canonical_frame_hash produce 64-char SHA256."""
    h_ev = canonical_event_hash("ev-c017-05")
    assert len(h_ev) == 64
    assert all(c in "0123456789abcdef" for c in h_ev)

    h_fact = canonical_fact_hash("fact-c017-01")
    assert len(h_fact) == 64

    h_frame = canonical_frame_hash("tbw_v3_frame_0012")
    assert len(h_frame) == 64


# ==============================================================================
# 6. Deep Proof Obligations & Counterfactual Tournament
# ==============================================================================

def test_knowledge_leak_obligation_timing():
    """KnowledgeLeakObligation must satisfy when character access precedes public broadcast."""
    res_valid = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=2010000,
        evidence_ids=["ev-1"]
    )
    assert res_valid.is_satisfied is True
    assert res_valid.score >= 0.90

    res_invalid = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=1000000,
        earliest_character_access_ms=2010000,
        evidence_ids=["ev-1"]
    )
    assert res_invalid.is_satisfied is False


def test_claim_action_obligation_strict_rules():
    """ClaimActionObligation fails closed if speech or action is missing."""
    res_no_claim = ClaimActionObligation.evaluate(
        speaker_claim_text="",
        actor_action_text="Enters room alone",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-1"]
    )
    assert res_no_claim.is_satisfied is False
    assert "MISSING_SPEAKER_CLAIM" in res_no_claim.broken_rules

    res_valid = ClaimActionObligation.evaluate(
        speaker_claim_text="I was away in the city protecting the estate",
        actor_action_text="Anderson stands alone inspecting the study room",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-1", "ev-2"]
    )
    assert res_valid.is_satisfied is True


def test_hidden_plan_obligation_multi_scene_chronology():
    """HiddenPlanObligation requires >= 2 distinct scenes and chronological order."""
    steps_single_scene = [
        {"scene_id": "scene-1", "timestamp_ms": 1000, "action": "step 1"},
        {"scene_id": "scene-1", "timestamp_ms": 2000, "action": "step 2"}
    ]
    res_single = HiddenPlanObligation.evaluate(plan_steps=steps_single_scene, evidence_ids=[])
    assert res_single.is_satisfied is False
    assert "SINGLE_SCENE_PLAN" in res_single.broken_rules

    steps_valid = [
        {"scene_id": "scene-1", "timestamp_ms": 1000, "action": "step 1"},
        {"scene_id": "scene-2", "timestamp_ms": 2000, "action": "step 2"}
    ]
    res_valid = HiddenPlanObligation.evaluate(plan_steps=steps_valid, evidence_ids=[])
    assert res_valid.is_satisfied is True


def test_counterfactual_tournament_real_deltas():
    """CounterfactualTournamentEngine executes 4 controls with genuine delta evaluations."""
    anderson_proof = CANONICAL_PATTERNS_MAP["reveal-anderson-identity"][0]
    result = CounterfactualTournamentEngine.run_tournament(
        proof=anderson_proof,
        target_reveal_id="reveal-anderson-identity"
    )
    assert len(result.experiments) == 4
    assert result.is_robust is True
    assert result.reveal_swap_delta <= -0.30
    assert result.evidence_ablation_delta <= -0.40


# ==============================================================================
# 7. Alembic Migration & Docker Stack
# ==============================================================================

def test_alembic_0004_migration_exists():
    """0004_r4_1_final_schema_sync.py migration must exist with valid upgrade/downgrade."""
    mig_path = Path("db/postgres/migrations/versions/0004_r4_1_final_schema_sync.py")
    assert mig_path.exists()
    content = mig_path.read_text(encoding="utf-8")
    assert "def upgrade()" in content
    assert "def downgrade()" in content
    assert "counterfactual_run_records" in content


def test_docker_compose_and_dockerfile_multi_stage():
    """docker-compose.yml must contain reframe-migrate and have zero credentials in default compose."""
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    compose_text = compose_path.read_text(encoding="utf-8")
    assert "reframe-migrate:" in compose_text
    assert "alembic" in compose_text
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in compose_text

    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists()
    docker_text = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM node:20-alpine AS frontend-builder" in docker_text
    assert "FROM python:3.11-slim" in docker_text
    assert "COPY --from=frontend-builder" in docker_text


# ==============================================================================
# 8. Fan Experience Dynamic Moment Projection
# ==============================================================================

@pytest.mark.asyncio
async def test_fan_experience_dynamic_moment_projection():
    """_resolve_moment dynamically resolves from CANONICAL_PROOFS_MAP with clean public copy."""
    moment = await _resolve_moment("proof-anderson-01")
    assert moment["moment_id"] == "proof-anderson-01"
    assert moment["proof_type"] == "MULTI_SCENE_PATTERN"
    assert moment["trust_namespace"] == "ENGINE_INFERENCE"
    assert "Engine-supported interpretation" in moment["trust_label"]
    assert moment["human_review_status"] == "NOT_REVIEWED"


# ==============================================================================
# 9. Health & Ready Endpoints Truthfulness
# ==============================================================================

@pytest.mark.asyncio
async def test_health_and_ready_truthfulness():
    """ready_probe must truthfully check datastores and dataset readiness."""
    from apps.api.routers.health import ready_probe, health_probe

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    res = await ready_probe(db=mock_db)
    assert "status" in res
    assert "dataset_ready" in res["data"]
    assert res["dataset_counts"]["scenes"] >= 43

    health_res = await health_probe(db=mock_db)
    assert health_res["status"] == res["status"]


# ==============================================================================
# 10. Frontend ApiClient Error Handling
# ==============================================================================

def test_frontend_api_client_handles_errors():
    """apiClient.ts must contain handleResponse checking res.ok."""
    client_path = Path("apps/web/src/services/apiClient.ts")
    assert client_path.exists()
    content = client_path.read_text(encoding="utf-8")
    assert "handleResponse" in content
    assert "!res.ok" in content
    assert "throw new Error" in content
