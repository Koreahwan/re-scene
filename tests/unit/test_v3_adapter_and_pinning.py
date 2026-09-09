"""
Unit Tests for V3 Evidence Adapter, Version Pinning, and Canonical Corrections
"""
import pytest
from sqlalchemy import select

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.evidence.models import EvidenceCatalog
from src.reframe.evidence.sync import evidence_synchronizer
from src.reframe.evidence.repository import evidence_repo


def test_v3_dataset_exact_counts():
    scenes = v3_adapter.get_scenes()
    events = v3_adapter.get_events()
    facts = v3_adapter.get_facts()
    reveals = v3_adapter.get_reveals()

    assert len(scenes) == 43, f"Expected 43 scenes, got {len(scenes)}"
    assert len(events) == 187, f"Expected 187 events, got {len(events)}"
    assert len(facts) == 94, f"Expected 94 facts, got {len(facts)}"
    assert len(reveals) == 4, f"Expected 4 reveals, got {len(reveals)}"


def test_v3_canonical_corrections_overlay():
    # Check that ev-c041-02 has the correction applied
    ev_c041_02 = v3_adapter.get_event("ev-c041-02")
    assert ev_c041_02 is not None
    assert ev_c041_02.is_corrected is True
    assert ev_c041_02.actor == "Police and Household"
    assert "Detective Anderson" not in ev_c041_02.actor
    assert ev_c041_02.correction_overlay_sha is not None

    # Check that ev-c041-03 has the correction applied
    ev_c041_03 = v3_adapter.get_event("ev-c041-03")
    assert ev_c041_03 is not None
    assert ev_c041_03.is_corrected is True
    assert ev_c041_03.actor == "Police Officers"
    assert ev_c041_03.correction_overlay_sha is not None


def test_v3_evidence_ref_generation():
    scene_ref = v3_adapter.get_evidence_ref("scene", "scene-tbw-c001")
    assert scene_ref is not None
    assert scene_ref.work_id == "the-bat-whispers-1930"
    assert scene_ref.edition_id == "tbw-fullscreen-archive"
    assert scene_ref.dataset_version == "v3"
    assert len(scene_ref.evidence_content_hash) == 64

    event_ref = v3_adapter.get_evidence_ref("event", "ev-c041-02")
    assert event_ref is not None
    assert event_ref.correction_overlay_sha is not None


def test_zero_future_scene_leakage_enforcement():
    anderson_cutoff = 4860000  # Reveal timestamp
    prior_scenes = evidence_repo.get_scenes(cutoff_ms=anderson_cutoff)

    # Every scene retrieved must start before the cutoff
    assert len(prior_scenes) > 0
    for s in prior_scenes:
        assert s.start_ms < anderson_cutoff, f"Future scene {s.scene_id} at {s.start_ms}ms leaked past {anderson_cutoff}ms"

    # Future scenes must be excluded
    future_scenes = [s for s in v3_adapter.get_scenes() if s.start_ms >= anderson_cutoff]
    for fs in future_scenes:
        assert fs.scene_id not in [s.scene_id for s in prior_scenes]


@pytest.mark.asyncio
async def test_evidence_catalog_database_sync():
    async with AsyncSessionLocal() as db:
        synced_count = await evidence_synchronizer.sync_evidence_catalog(db)
        await db.commit()

        # Query total entries in evidence_catalog
        stmt = select(EvidenceCatalog)
        res = await db.execute(stmt)
        entries = res.scalars().all()
        assert len(entries) >= 43 + 187 + 94
