"""
Reframe V7 Fan Experience API Contract Tests (Quick Wow, Rewatch Sync, Trust Label, Deep Dive)
Audits removal of CANONICAL_MOMENTS_MAP authority and verifies D3 RewatchPattern mappings.
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from apps.api.routers.fan_experience import _resolve_moment
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User
from src.reframe.identity.auth import create_session_token, generate_csrf_token, ViewerContext
from src.reframe.proof.store import CANONICAL_PROOFS_MAP, CANONICAL_PATTERNS_MAP


async def _setup_admin_client(client: AsyncClient, completed_reveals=None) -> str:
    """Helper to authenticate client as ADMIN with specified completed reveals."""
    admin_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        admin_user = User(
            id=admin_id,
            email_normalized=f"admin_{admin_id.hex[:6]}@reframe.dev",
            role="ADMIN",
            status="ACTIVE"
        )
        db.add(admin_user)
        await db.commit()

    token = create_session_token(admin_id, "ADMIN")
    client.cookies.set(settings.SESSION_COOKIE_NAME, token)
    csrf = generate_csrf_token(token)

    if completed_reveals:
        await client.put(
            "/api/v1/me/watch-progress/the-bat-whispers-1930",
            headers={"X-CSRF-Token": csrf},
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "COMPLETED",
                "progress_ms": 5040000,
                "completed_reveal_ids": completed_reveals
            }
        )
    return csrf


@pytest.mark.asyncio
async def test_legacy_moment_knowledge_leak_normal_viewer_hidden_404():
    """
    Test 1: moment-anderson-knowledge-leak as normal viewer (guest or user)
    must NOT expose legacy Verified Canon content and must return 404 because
    the underlying D3 pattern is HIDDEN_FROM_PUBLIC.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moment_id = "moment-anderson-knowledge-leak"

        # 1. Guest request -> 404
        res_guest = await client.get(f"/api/v1/moments/{moment_id}/quick-wow")
        assert res_guest.status_code == 404

        # 2. Normal authenticated fan (USER role) -> 404
        login_res = await client.post("/api/v1/auth/dev-login", json={
            "email": "fan_user@reframe.dev",
            "display_name": "Detective Fan"
        })
        token = login_res.cookies.get(settings.SESSION_COOKIE_NAME)
        csrf = login_res.json()["data"]["csrf_token"]
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        await client.put(
            "/api/v1/me/watch-progress/the-bat-whispers-1930",
            headers={"X-CSRF-Token": csrf},
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "COMPLETED",
                "progress_ms": 5040000,
                "completed_reveal_ids": ["reveal-anderson-identity"]
            }
        )

        res_user = await client.get(f"/api/v1/moments/{moment_id}/quick-wow")
        assert res_user.status_code == 404


@pytest.mark.asyncio
async def test_legacy_moment_knowledge_leak_admin_rewatch_pattern():
    """
    Test 2: moment-anderson-knowledge-leak as admin resolves to REWATCH_PATTERN,
    ENGINE_INFERENCE, NOT_VALIDATED, with no fabricated blueprint claim or Verified Canon badge.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moment_id = "moment-anderson-knowledge-leak"
        await _setup_admin_client(client, completed_reveals=["reveal-anderson-identity"])

        # Quick-wow inspection
        res_quick = await client.get(f"/api/v1/moments/{moment_id}/quick-wow")
        assert res_quick.status_code == 200
        data_quick = res_quick.json()["data"]
        assert data_quick["visibility"] == "VISIBLE"
        assert data_quick["proof_badge"] == "Rewatch Pattern"
        assert "Verified Canon" not in data_quick["proof_badge"]
        assert data_quick["trust_namespace"] == "ENGINE_INFERENCE"
        assert data_quick["title"] == "Detective Anderson Performs Unbriefed Search Operations"
        assert "Anderson already knew the blueprint" not in data_quick["after_understanding"]

        # Trust label inspection
        res_trust = await client.get(f"/api/v1/moments/{moment_id}/trust-label")
        assert res_trust.status_code == 200
        data_trust = res_trust.json()["data"]
        assert data_trust["verification_status"] == "ENGINE_INFERENCE"
        assert data_trust["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"
        assert "reveal_swap_delta" not in data_trust["counterfactual_robustness"]

        # Deep dive inspection
        res_deep = await client.get(f"/api/v1/moments/{moment_id}/deep-dive")
        assert res_deep.status_code == 200
        data_deep = res_deep.json()["data"]
        assert data_deep["counterfactual_delta"] is None
        assert data_deep["display_salience_estimate"] == 0.85
        assert data_deep["display_heuristic_impact"] == 0.85


@pytest.mark.asyncio
async def test_legacy_moment_claim_action_conflict_no_unsupported_text():
    """
    Test 3: moment-anderson-claim-action-conflict must resolve to pattern-anderson-02
    and must not return unsupported legacy claim text.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moment_id = "moment-anderson-claim-action-conflict"
        await _setup_admin_client(client, completed_reveals=["reveal-anderson-identity"])

        res = await client.get(f"/api/v1/moments/{moment_id}/rewatch-sync")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["visibility"] == "VISIBLE"
        assert data["title"] == "Phased Architectural Blueprint Review and Structural Fixture Search Pattern"
        # Must not contain unsupported fabricated claims
        assert "promises Cornelia the premises are secure" not in data.get("companion_notes", "")
        assert "cuts the main hallway illumination" not in data.get("companion_notes", "")


@pytest.mark.asyncio
async def test_legacy_moment_secret_room_fireplace_mechanism_discovery():
    """
    Test 4: moment-secret-room-fireplace must resolve to pattern-secret-room-01
    (MECHANISM_DISCOVERY) and not return KnowledgeLeak Verified Canon.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        moment_id = "moment-secret-room-fireplace"
        await _setup_admin_client(client, completed_reveals=["reveal-secret-room-location"])

        res = await client.get(f"/api/v1/moments/{moment_id}/trust-label")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["verification_status"] == "ENGINE_INFERENCE"
        assert data["proof_type"] == "MECHANISM_DISCOVERY"
        assert data["proof_type"] != "KNOWLEDGE_LEAK"
        assert data["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"


@pytest.mark.asyncio
async def test_canonical_proofs_map_empty_no_verified_proof():
    """
    Test 5: CANONICAL_PROOFS_MAP is empty -> no Verified Proof is generated from static registry.
    """
    assert len(CANONICAL_PROOFS_MAP) == 0

    admin_viewer = ViewerContext(
        user_id=uuid.uuid4(),
        roles=["ADMIN"],
        completed_reveal_ids=["reveal-anderson-identity", "reveal-secret-room-location"]
    )

    resolved_anderson = await _resolve_moment("pattern-anderson-01", viewer=admin_viewer)
    assert resolved_anderson["content_kind"] == "REWATCH_PATTERN"
    assert resolved_anderson["verification_status"] != "VERIFIED_CANON"

    resolved_secret = await _resolve_moment("pattern-secret-room-01", viewer=admin_viewer)
    assert resolved_secret["content_kind"] == "REWATCH_PATTERN"
    assert resolved_secret["verification_status"] != "VERIFIED_CANON"


@pytest.mark.asyncio
async def test_no_counterfactually_robust_or_default_delta_on_rewatch_pattern():
    """
    Test 6: No literal 'COUNTERFACTUALLY_ROBUST' or default `-0.85` may be applied to a REWATCH_PATTERN.
    """
    admin_viewer = ViewerContext(
        user_id=uuid.uuid4(),
        roles=["ADMIN"],
        completed_reveal_ids=["reveal-anderson-identity", "reveal-secret-room-location"]
    )

    for rev_id, patterns in CANONICAL_PATTERNS_MAP.items():
        for p in patterns:
            pid = p.get("pattern_id") or p.get("proof_id")
            resolved = await _resolve_moment(pid, viewer=admin_viewer)
            assert resolved["content_kind"] == "REWATCH_PATTERN"
            assert resolved["counterfactual_robustness"]["verdict"] == "NOT_VALIDATED"
            assert resolved["counterfactual_robustness"]["verdict"] != "COUNTERFACTUALLY_ROBUST"
            assert resolved["counterfactual_delta"] is None


@pytest.mark.asyncio
async def test_unknown_moment_404():
    """Test 7: Unknown moment ID returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/moments/non-existent-moment/quick-wow")
        assert res.status_code == 404
