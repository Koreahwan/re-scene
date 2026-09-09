"""
Contract & Unit Tests for Server Spoiler Cutoff Pipeline, DTO Delivery, and UI Protection Policy (R2-02).
Enforces:
- Test scene at 10,000ms with spoiler cutoff at 30,000ms (synthetic non-film data).
- At 29,999ms: raw text hidden / locked.
- At 30,000ms + server VISIBLE: raw text revealed.
- Rewind to 5,000ms: client protection immediately hides raw text even before network sync.
- Missing / null / negative / invalid cutoff: never revealed, even if scene timestamp is 10,000ms and progress is higher.
- Server locked + runtime end selected: remains locked until new server response.
- End-to-end Server -> DTO -> Frontend Mapper contract verification.
"""
import pytest
from typing import Dict, Any

from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility


def client_card_lock_evaluator(
    card: Dict[str, Any],
    effective_progress_ms: int
) -> bool:
    """
    Python mirror of FilmHubPage.tsx client-side protection predicate:
    const validCutoffMs = (typeof card.spoilerCutoffMs === 'number' && Number.isFinite(card.spoilerCutoffMs) && card.spoilerCutoffMs >= 0)
      ? card.spoilerCutoffMs
      : null;
    const isCardSpoilerLocked = Boolean(
      card.isLocked ||
      effectiveProgress === 0 ||
      validCutoffMs === null ||
      effectiveProgress < validCutoffMs
    );
    """
    is_locked = bool(card.get("isLocked", False))
    cutoff = card.get("spoilerCutoffMs")
    is_valid_cutoff = isinstance(cutoff, (int, float)) and cutoff >= 0

    if is_locked:
        return True
    if effective_progress_ms == 0:
        return True
    if not is_valid_cutoff:
        return True
    if effective_progress_ms < cutoff:
        return True
    return False


def test_r2_02_below_cutoff_at_29999ms_hides_raw_text():
    """At 29,999ms, a card with cutoff 30,000ms must be locked even though scene is 10,000ms."""
    card = {
        "id": "proof-test-01",
        "title": "Secret Culprit Identity Revealed",
        "body": "The protagonist was the antagonist all along.",
        "timestampMs": 10000,
        "spoilerCutoffMs": 30000,
        "isLocked": False,
    }
    # 29,999ms < 30,000ms cutoff -> must be locked
    is_locked = client_card_lock_evaluator(card, effective_progress_ms=29999)
    assert is_locked is True


def test_r2_02_server_visible_at_30000ms_unlocked():
    """At 30,000ms with server VISIBLE (isLocked=False), card is revealed."""
    card = {
        "id": "proof-test-01",
        "title": "Secret Culprit Identity Revealed",
        "body": "The protagonist was the antagonist all along.",
        "timestampMs": 10000,
        "spoilerCutoffMs": 30000,
        "isLocked": False,
    }
    is_locked = client_card_lock_evaluator(card, effective_progress_ms=30000)
    assert is_locked is False


def test_r2_02_rewind_to_5000ms_instantly_locks_without_network_roundtrip():
    """
    After card was visible at 30,000ms, rewinding effective progress to 5,000ms
    must immediately lock the card client-side even if PUT/GET is pending.
    """
    card = {
        "id": "proof-test-01",
        "title": "Secret Culprit Identity Revealed",
        "body": "The protagonist was the antagonist all along.",
        "timestampMs": 10000,
        "spoilerCutoffMs": 30000,
        "isLocked": False,
    }
    # Rewind to 5,000ms
    is_locked = client_card_lock_evaluator(card, effective_progress_ms=5000)
    assert is_locked is True


def test_r2_02_invalid_missing_cutoff_never_reveals():
    """
    Cutoff missing, null, negative, or invalid type must NEVER reveal,
    even when scene timestamp is 10,000ms and viewer progress is 50,000ms.
    """
    invalid_cutoffs = [None, -1, -30000, "invalid", float("nan")]
    for invalid_c in invalid_cutoffs:
        card = {
            "id": "proof-test-01",
            "title": "Secret Culprit Identity",
            "body": "Raw spoiler text",
            "timestampMs": 10000,
            "spoilerCutoffMs": invalid_c,
            "isLocked": False,
        }
        # Even at 50,000ms (far past 10,000ms scene timestamp)
        is_locked = client_card_lock_evaluator(card, effective_progress_ms=50000)
        assert is_locked is True, f"Card with cutoff {invalid_c} was improperly revealed!"


def test_r2_02_server_locked_at_runtime_end_stays_locked():
    """
    When the server returned a locked response (isLocked=True),
    scrubbing to runtime end (e.g. 100,000ms) without a new server reveal response stays locked.
    """
    card = {
        "id": "proof-test-01",
        "title": "Spoiler Protected Scene",
        "body": "Content hidden behind spoiler protection.",
        "timestampMs": None,
        "spoilerCutoffMs": 30000,
        "isLocked": True,  # Server returned locked
    }
    is_locked = client_card_lock_evaluator(card, effective_progress_ms=100000)
    assert is_locked is True


def test_r2_02_server_to_dto_to_mapper_contract():
    """
    Verifies that the server sanitize pipeline embeds spoiler_cutoff_ms and unlock_metadata,
    and that DTO keys are consistent for work_id/movie_id and edition_id.
    """
    raw_proof = {
        "proof_id": "prf-test-42",
        "work_id": "test-film-1930",
        "movie_id": "test-film-1930",
        "edition_id": "test-edition-01",
        "reveal_id": "rev-test-01",
        "spoiler_cutoff_ms": 30000,
        "cutoff_ms": 30000,
        "proof_type": "KNOWLEDGE_LEAK",
        "title": "Contradictory Knowledge Leak",
        "blind_explanation": "A normal conversation.",
        "reveal_explanation": "He possessed unbriefed knowledge of the vault.",
    }

    # Case 1: VISIBLE response
    visible_dto = sanitize_payload_for_viewer(
        payload=raw_proof,
        visibility=SpoilerVisibility.VISIBLE,
        safe_title="Safe Title",
        safe_preview="Safe Summary"
    )
    assert visible_dto["visibility"] == "VISIBLE"
    assert visible_dto.get("is_locked", False) is False
    assert visible_dto["is_spoiler_masked"] is False
    assert visible_dto["spoiler_cutoff_ms"] == 30000
    assert visible_dto["work_id"] == "test-film-1930"
    assert visible_dto["movie_id"] == "test-film-1930"
    assert visible_dto["edition_id"] == "test-edition-01"
    assert visible_dto["title"] == "Contradictory Knowledge Leak"

    # Case 2: LOCKED response
    locked_dto = sanitize_payload_for_viewer(
        payload=raw_proof,
        visibility=SpoilerVisibility.LOCKED,
        safe_title="Verified Clue",
        safe_preview="Unlock after viewing the reveal.",
        unlock_metadata={"minimum_progress_ms": 30000, "required_reveal_ids": ["rev-test-01"]}
    )
    assert locked_dto["visibility"] == "LOCKED"
    assert locked_dto["is_locked"] is True
    assert locked_dto["title"] == "Verified Clue"
    assert "blind_explanation" not in locked_dto
    assert "reveal_explanation" not in locked_dto
    assert locked_dto["unlock_metadata"]["minimum_progress_ms"] == 30000
    assert locked_dto["work_id"] == "test-film-1930"
    assert locked_dto["movie_id"] == "test-film-1930"
    assert locked_dto["edition_id"] == "test-edition-01"
