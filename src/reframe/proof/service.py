"""
Reframe V7 Proof Service
"""
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.proof.models import ProofRecord
from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility

logger = structlog.get_logger(__name__)


class ProofService:
    @staticmethod
    async def save_proof(
        db: AsyncSession,
        proof_data: Dict[str, Any],
        work_id: str,
        edition_id: str,
        reveal_id: str
    ) -> ProofRecord:
        proof_id = proof_data["proof_id"]
        stmt = select(ProofRecord).where(ProofRecord.proof_id == proof_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        if not record:
            record = ProofRecord(
                id=uuid.uuid4(),
                proof_id=proof_id,
                work_id=work_id,
                edition_id=edition_id,
                dataset_version="v3",
                reveal_id=reveal_id,
                proof_type=proof_data["proof_type"],
                title=proof_data["title"],
                blind_explanation=proof_data["blind_explanation"],
                reveal_explanation=proof_data["reveal_explanation"],
                evidence_chain=proof_data["evidence_chain"],
                observed_premises=proof_data["observed_premises"],
                alternative_explanations=proof_data["alternative_explanations"],
                counterfactual_results=proof_data["counterfactual_results"],
                proof_strength=proof_data.get("proof_strength", 0.90),
                fan_impact=proof_data.get("fan_impact", 0.85)
            )
            db.add(record)
            await db.flush()
        return record

    @staticmethod
    async def get_proofs_for_reveal(
        db: AsyncSession,
        reveal_id: str,
        viewer: ViewerContext
    ) -> List[Dict[str, Any]]:
        stmt = select(ProofRecord).where(ProofRecord.reveal_id == reveal_id).order_by(ProofRecord.fan_impact.desc())
        res = await db.execute(stmt)
        records = res.scalars().all()

        scope = SpoilerScope(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            minimum_progress_ms=4860000,
            required_reveal_ids=[reveal_id],
            severity="ENDING",
            safe_title="Investigative Narrative Clue",
            safe_preview="Narrative clue unlocked upon viewing reveal."
        )
        visibility = evaluate_spoiler_visibility(scope, viewer)

        out = []
        for r in records:
            raw_payload = {
                "proof_id": r.proof_id,
                "reveal_id": r.reveal_id,
                "proof_type": r.proof_type,
                "title": r.title,
                "blind_explanation": r.blind_explanation,
                "reveal_explanation": r.reveal_explanation,
                "evidence_chain": r.evidence_chain,
                "observed_premises": r.observed_premises,
                "alternative_explanations": r.alternative_explanations,
                "counterfactual_results": r.counterfactual_results,
                "proof_strength": r.proof_strength,
                "fan_impact": r.fan_impact
            }
            sanitized = sanitize_payload_for_viewer(
                payload=raw_payload,
                visibility=visibility,
                safe_title=f"Verified Clue ({r.proof_type})"
            )
            out.append(sanitized)
        return out


proof_service = ProofService()
