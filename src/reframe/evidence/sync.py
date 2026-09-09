"""
Reframe V7 Evidence Catalog Database Synchronizer
"""
import uuid
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.evidence.models import EvidenceCatalog
from src.reframe.evidence.adapter import v3_adapter

logger = structlog.get_logger(__name__)


class EvidenceCatalogSynchronizer:
    @staticmethod
    async def sync_evidence_catalog(db: AsyncSession) -> int:
        """
        Synchronizes all V3 scenes, events, and facts into the PostgreSQL evidence_catalog table.
        """
        synced_count = 0

        # 1. Sync Scenes
        for scene in v3_adapter.get_scenes():
            stmt = select(EvidenceCatalog).where(
                EvidenceCatalog.work_id == scene.work_id,
                EvidenceCatalog.edition_id == scene.edition_id,
                EvidenceCatalog.dataset_version == scene.dataset_version,
                EvidenceCatalog.evidence_type == "scene",
                EvidenceCatalog.evidence_id == scene.scene_id
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()

            if not existing:
                catalog_entry = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id=scene.work_id,
                    edition_id=scene.edition_id,
                    dataset_version=scene.dataset_version,
                    evidence_type="scene",
                    evidence_id=scene.scene_id,
                    evidence_hash=scene.evidence_hash,
                    screen_start_ms=scene.start_ms,
                    screen_end_ms=scene.end_ms,
                    status="ACTIVE"
                )
                db.add(catalog_entry)
                synced_count += 1

        # 2. Sync Events
        for event in v3_adapter.get_events():
            stmt = select(EvidenceCatalog).where(
                EvidenceCatalog.work_id == event.work_id,
                EvidenceCatalog.edition_id == event.edition_id,
                EvidenceCatalog.dataset_version == event.dataset_version,
                EvidenceCatalog.evidence_type == "event",
                EvidenceCatalog.evidence_id == event.event_id
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()

            if not existing:
                catalog_entry = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id=event.work_id,
                    edition_id=event.edition_id,
                    dataset_version=event.dataset_version,
                    evidence_type="event",
                    evidence_id=event.event_id,
                    evidence_hash=event.evidence_hash,
                    correction_overlay_sha=event.correction_overlay_sha,
                    screen_start_ms=event.evidence_start_ms,
                    screen_end_ms=event.evidence_end_ms,
                    status="ACTIVE"
                )
                db.add(catalog_entry)
                synced_count += 1

        # 3. Sync Facts
        for fact in v3_adapter.get_facts():
            stmt = select(EvidenceCatalog).where(
                EvidenceCatalog.work_id == fact.work_id,
                EvidenceCatalog.edition_id == fact.edition_id,
                EvidenceCatalog.dataset_version == fact.dataset_version,
                EvidenceCatalog.evidence_type == "fact",
                EvidenceCatalog.evidence_id == fact.fact_id
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()

            if not existing:
                catalog_entry = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id=fact.work_id,
                    edition_id=fact.edition_id,
                    dataset_version=fact.dataset_version,
                    evidence_type="fact",
                    evidence_id=fact.fact_id,
                    evidence_hash=fact.evidence_hash,
                    screen_start_ms=fact.timestamp_ms,
                    screen_end_ms=fact.timestamp_ms,
                    status="ACTIVE"
                )
                db.add(catalog_entry)
                synced_count += 1

        await db.flush()
        logger.info("Evidence catalog synchronized", new_entries=synced_count)
        return synced_count


evidence_synchronizer = EvidenceCatalogSynchronizer()
