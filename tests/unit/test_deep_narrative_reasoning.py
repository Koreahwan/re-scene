"""
Unit Tests for V6/V7 Deep Narrative Reasoning, Blindness, Proof Obligations, and Counterfactuals
"""
import uuid
import pytest
from sqlalchemy import select

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.narrative.blindness import blind_alias
from src.reframe.narrative.reveal_compiler import reveal_compiler
from src.reframe.narrative.counterfactual import counterfactual_engine
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.proof.service import proof_service
from src.reframe.identity.auth import ViewerContext


def test_blind_alias_pipeline():
    text = "Detective Anderson enters Oakdale Manor chasing The Bat."
    anonymized = blind_alias.anonymize_text(text)
    assert "Anderson" not in anonymized
    assert "Oakdale Manor" not in anonymized
    assert "The Bat" not in anonymized
    assert "PERSON_07" in anonymized
    assert "LOCATION_03" in anonymized
    assert "MASKED_ENTITY_02" in anonymized

    restored = blind_alias.deanonymize_text(anonymized)
    assert "Detective Anderson" in restored
    assert "Oakdale Manor" in restored
    assert "The Bat" in restored


def test_reveal_compiler_p0_reveals():
    anderson_reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    assert anderson_reveal is not None
    prog = reveal_compiler.compile(anderson_reveal)
    assert prog.reveal_type == "IDENTITY"
    assert "KNOWLEDGE_LEAK" in prog.proof_obligations
    assert "CLAIM_ACTION_CONFLICT" in prog.proof_obligations
    assert "HIDDEN_PLAN_CHAIN" in prog.proof_obligations
    assert "REQUIRES_KNOWLEDGE_OF" in prog.required_graph_edges

    secret_room_reveal = v3_adapter.get_reveal("reveal-secret-room-location")
    assert secret_room_reveal is not None
    secret_prog = reveal_compiler.compile(secret_room_reveal)
    assert secret_prog.reveal_type == "LOCATION"
    assert "ENABLES" in secret_prog.required_graph_edges


def test_counterfactual_tournament_engine():
    robust_proof = {
        "proof_id": "test-proof-01",
        "proof_type": "MULTI_SCENE_PATTERN",
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone in the dark hall inspecting his surroundings."
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries rolled papers and unrolls blueprints of the bank safe."
            }
        ]
    }
    result = counterfactual_engine.run_tournament(robust_proof, target_reveal_id="reveal-anderson-identity")
    assert result.is_robust is True
    assert result.reveal_swap_delta <= -0.30


    fragile_proof = {
        "proof_id": "test-proof-fragile",
        "observed_premises": [
            {"event_id": "ev-02", "fact": "Unrelated garden fountain in manor grounds"}
        ]
    }
    fragile_res = counterfactual_engine.run_tournament(fragile_proof, target_reveal_id="reveal-anderson-identity")
    assert fragile_res.is_robust is False

    assert len(fragile_res.rejection_reasons) >= 2


@pytest.mark.asyncio
async def test_proof_persistence_and_spoiler_masking():
    async with AsyncSessionLocal() as db:
        proof_data = {
            "proof_id": f"test-proof-{uuid.uuid4().hex[:8]}",
            "proof_type": "KNOWLEDGE_LEAK",
            "title": "Detective Anderson Manipulates Room Keys",
            "blind_explanation": "Searching for a missing guest.",
            "reveal_explanation": "Anderson needed the key because he is The Bat.",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c011", "timestamp_ms": 1320000},
                {"scene_id": "scene-tbw-c017", "timestamp_ms": 2040000}
            ],
            "observed_premises": [
                {"event_id": "ev-c011-01", "scene_id": "scene-tbw-c011", "timestamp_ms": 1320000}
            ],
            "alternative_explanations": ["Accidental discovery"],
            "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65},
            "proof_strength": 0.94,
            "fan_impact": 0.91
        }
        await proof_service.save_proof(
            db=db,
            proof_data=proof_data,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity"
        )
        await db.commit()

        # Unwatched guest gets redacted locked clue
        guest = ViewerContext(roles=["GUEST"])
        guest_proofs = await proof_service.get_proofs_for_reveal(db, "reveal-anderson-identity", guest)
        assert len(guest_proofs) >= 1
        target_guest = next(p for p in guest_proofs if p["proof_id"] == proof_data["proof_id"])
        assert target_guest["visibility"] == "LOCKED"
        assert "Anderson" not in target_guest["title"]

        # Completed viewer gets full unmasked proof
        completed_viewer = ViewerContext(
            user_id=uuid.uuid4(),
            roles=["USER"],
            completed_reveal_ids=["reveal-anderson-identity"]
        )
        auth_proofs = await proof_service.get_proofs_for_reveal(db, "reveal-anderson-identity", completed_viewer)
        target_auth = next(p for p in auth_proofs if p["proof_id"] == proof_data["proof_id"])
        assert target_auth["visibility"] == "VISIBLE"
        assert target_auth["title"] == "Detective Anderson Manipulates Room Keys"
