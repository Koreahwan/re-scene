import os
import pytest
from reframe.domain.models import Reveal, ReframeCandidate
from reframe.domain.enums import RelationType
from reframe.verification.verifier import EvidenceVerifier
from reframe.mcp.gateway import MockNarrativeMemoryGateway


@pytest.mark.asyncio
async def test_strict_real_mode_forbids_all_local_fallbacks():
    """
    Guarantees that when REAL_INTEGRATION_VALIDATION=true:
    - Mock gateways are forbidden.
    - Deterministic verifiers are forbidden.
    - Autonomous local fallbacks are forbidden.
    - Unauthenticated requests fail honestly without silently succeeding via hidden fallback.
    """
    os.environ["REAL_INTEGRATION_VALIDATION"] = "true"
    try:
        # 1. Mock Gateway is forbidden
        with pytest.raises(RuntimeError, match="MOCK_GATEWAY_FORBIDDEN_IN_REAL_VALIDATION"):
            _ = MockNarrativeMemoryGateway(scenes=[], events=[], facts=[])

        verifier = EvidenceVerifier()
        # If client is None (no GEMINI_API_KEY)
        verifier.client = None

        reveal = Reveal(
            reveal_id="rev-1",
            movie_id="tbw-1930",
            timestamp_ms=1000,
            title="Test Reveal",
            reveal_type="IDENTITY",
            subject="Detective Anderson",
            predicate="is_identity_of",
            previous_belief="A",
            revealed_fact="B",
        )
        candidate = ReframeCandidate(
            reveal_id="rev-1",
            scene_id="scn-1",
            movie_id="tbw-1930",
            start_ms=100,
            summary="Test Scene",
        )

        # 2. verify_candidate raises when live client is missing
        with pytest.raises(RuntimeError, match="REAL_GEMINI_CLIENT_REQUIRED"):
            await verifier.verify_candidate(reveal, candidate, events=[], facts=[])

        # 3. verify_candidate_autonomous raises
        with pytest.raises(RuntimeError, match="AUTONOMOUS_FALLBACK_FORBIDDEN"):
            verifier.verify_candidate_autonomous(reveal, candidate, events=[], facts=[])

        # 4. verify_candidate_deterministic raises
        with pytest.raises(RuntimeError, match="DETERMINISTIC_VERIFIER_FORBIDDEN"):
            verifier.verify_candidate_deterministic(reveal, candidate, events=[], facts=[], pre_annotated_relation=RelationType.REINTERPRETATION)
    finally:
        os.environ["REAL_INTEGRATION_VALIDATION"] = "false"
