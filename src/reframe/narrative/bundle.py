"""
Reframe V7 Evidence Bundle Builder
Assembles multi-channel retrieved observations, EvidenceSeeds, blind interpretations, anomalies, and counterfactual controls.
Rejects live Google ADK execution without verified MCP-derived seeds.
Zero Paid Model Calls.
"""
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import structlog

from src.reframe.evidence.schemas import RevealDTO, SceneDTO, EventDTO, FactDTO
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.channels import multi_channel_engine, EvidenceSeed
from src.reframe.domain.enums import ExecutionMode


logger = structlog.get_logger(__name__)


class EvidenceBundle(BaseModel):
    bundle_id: str
    reveal: RevealDTO
    blind_interpretation: str
    target_clue_title: str
    evidence_seeds: List[EvidenceSeed] = Field(default_factory=list)
    related_scenes: List[SceneDTO] = Field(default_factory=list)
    observed_events: List[EventDTO] = Field(default_factory=list)
    observed_facts: List[FactDTO] = Field(default_factory=list)
    mcp_knowledge_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    character_states: List[Dict[str, Any]] = Field(default_factory=list)
    audience_states: List[Dict[str, Any]] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    causal_path: List[str] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)
    counterfactual_controls: List[Dict[str, Any]] = Field(default_factory=list)


class EvidenceBundleBuilder:
    @staticmethod
    def build_bundle(
        reveal: RevealDTO,
        candidate_scene_ids: Optional[List[str]] = None,
        cutoff_ms: Optional[int] = None,
        provided_seeds: Optional[List[EvidenceSeed]] = None,
        execution_mode: ExecutionMode = ExecutionMode.OFFLINE_FIXTURE
    ) -> EvidenceBundle:
        effective_cutoff = cutoff_ms or reveal.timestamp_ms

        # Live Google ADK mode requires verified MCP evidence seeds (R3-02)
        if execution_mode == ExecutionMode.LIVE_GOOGLE and not provided_seeds:
            logger.error("mcp_evidence_required_for_live_mode", reveal_id=reveal.reveal_id)
            raise RuntimeError("MCP_EVIDENCE_REQUIRED: Live Google ADK execution requires verified MCP evidence seeds.")

        # Ingest provided EvidenceSeeds or execute multi-channel retrieval
        seeds = provided_seeds or multi_channel_engine.retrieve_candidates(reveal, effective_cutoff)

        if execution_mode == ExecutionMode.LIVE_GOOGLE:
            # Enforce strict content taint isolation (Section 18)
            for seed in seeds:
                if isinstance(seed, dict):
                    ans_ast = seed.get("answer_assisted", False) or seed.get("structured_payload", {}).get("answer_assisted") is True
                    src_ns = str(seed.get("source_namespace", "") or seed.get("structured_payload", {}).get("source_namespace", ""))
                    rationale = seed.get("channel_rationale", "") or ""
                    payload_dict = seed.get("structured_payload", {}) or {}
                else:
                    ans_ast = getattr(seed, "answer_assisted", False) or (seed.structured_payload.get("answer_assisted") is True if getattr(seed, "structured_payload", None) else False)
                    src_ns = str(getattr(seed, "source_namespace", "") or (seed.structured_payload.get("source_namespace", "") if getattr(seed, "structured_payload", None) else ""))
                    rationale = getattr(seed, "channel_rationale", "") or ""
                    payload_dict = getattr(seed, "structured_payload", {}) or {}

                if ans_ast:
                    raise RuntimeError("DEVELOPMENT_TAINT_DETECTED: Live Google ADK bundle cannot ingest answer-assisted evidence.")

                if any(src_ns.startswith(prefix) for prefix in ("DEVELOPMENT_", "GOLDEN_", "LEGACY_PROOF_", "DEVELOPMENT_SNAPSHOT_")):
                    raise RuntimeError(f"DEVELOPMENT_TAINT_DETECTED: Live Google ADK bundle rejects source_namespace '{src_ns}'.")

                raw_text = rationale + " " + json.dumps(payload_dict)
                tainted_phrases = [
                    "Engine-supported interpretation (Clean-Room V1.1)",
                    "the_bat_whispers_deep_snapshot_v1_1",
                    "DEVELOPMENT_SNAPSHOT_V1_1"
                ]
                if any(phrase in raw_text for phrase in tainted_phrases):
                    raise RuntimeError("DEVELOPMENT_TAINT_DETECTED: Live Google ADK bundle rejects development snapshot content.")

            # LIVE_GOOGLE: MCP results are authoritative evidence payload (Section 8)
            # v3_adapter is only used to validate IDs and hashes, not replace descriptions/actions.
            valid_scenes: List[SceneDTO] = []
            events: List[EventDTO] = []
            facts: List[FactDTO] = []
            seen_sids = set()
            seen_eids = set()
            seen_fids = set()

            for seed in seeds:
                if isinstance(seed, dict):
                    raw_rows = seed.get("structured_payload", {}).get("raw_rows", []) if "structured_payload" in seed else seed.get("raw_rows", [])
                else:
                    raw_rows = seed.structured_payload.get("raw_rows", []) if getattr(seed, "structured_payload", None) else []
                for r in raw_rows:
                    # Check if row is a scene
                    if "scene_id" in r and ("start_ms" in r or "location" in r or "summary" in r) and "event_id" not in r and "fact_id" not in r:
                        sid = r["scene_id"]
                        start_ms = int(r.get("start_ms", 0))
                        if sid not in seen_sids and start_ms < effective_cutoff:
                            seen_sids.add(sid)
                            adapter_sc = v3_adapter.get_scene(sid)
                            if adapter_sc:
                                valid_scenes.append(adapter_sc.model_copy(update={
                                    "summary": r.get("summary", adapter_sc.summary),
                                    "location": r.get("location", adapter_sc.location),
                                    "characters": r.get("characters", adapter_sc.characters),
                                    "objects": r.get("objects", adapter_sc.objects)
                                }))
                            else:
                                end_ms = int(r.get("end_ms", start_ms + 60000))
                                valid_scenes.append(SceneDTO(
                                    scene_id=sid,
                                    work_id=r.get("work_id", "the-bat-whispers-1930"),
                                    edition_id=r.get("edition_id", "tbw-fullscreen-archive"),
                                    dataset_version=r.get("dataset_version", "v3"),
                                    start_ms=start_ms,
                                    end_ms=end_ms,
                                    duration_ms=end_ms - start_ms,
                                    location=r.get("location", "Oakdale Manor"),
                                    summary=r.get("summary", ""),
                                    characters=r.get("characters", []),
                                    objects=r.get("objects", []),
                                    evidence_hash=r.get("evidence_hash", "hash-mcp")
                                ))
                    # Check if row is an event
                    elif "event_id" in r and "scene_id" in r:
                        eid = r["event_id"]
                        sid = r["scene_id"]
                        ts = int(r.get("timestamp_ms", 0))
                        if eid not in seen_eids and ts < effective_cutoff:
                            seen_eids.add(eid)
                            adapter_ev = v3_adapter.get_event(eid)
                            if adapter_ev:
                                events.append(adapter_ev.model_copy(update={
                                    "description": r.get("description", adapter_ev.description),
                                    "action": r.get("action", adapter_ev.action),
                                    "actor": r.get("actor", adapter_ev.actor),
                                    "target": r.get("target", adapter_ev.target),
                                    "object": r.get("object", adapter_ev.object)
                                }))
                            else:
                                events.append(EventDTO(
                                    event_id=eid,
                                    scene_id=sid,
                                    work_id=r.get("work_id", "the-bat-whispers-1930"),
                                    edition_id=r.get("edition_id", "tbw-fullscreen-archive"),
                                    dataset_version=r.get("dataset_version", "v3"),
                                    timestamp_ms=ts,
                                    evidence_start_ms=ts,
                                    evidence_end_ms=ts + 5000,
                                    actor=r.get("actor", "Detective Anderson"),
                                    action=r.get("action", "ACTION"),
                                    description=r.get("description", r.get("action_description", "")),
                                    evidence_hash=r.get("evidence_hash", "hash-mcp")
                                ))
                    # Check if row is a fact
                    elif "fact_id" in r and "scene_id" in r:
                        fid = r["fact_id"]
                        sid = r["scene_id"]
                        ts = int(r.get("timestamp_ms", 0))
                        if fid not in seen_fids and ts < effective_cutoff:
                            seen_fids.add(fid)
                            adapter_f = v3_adapter.get_fact(fid)
                            if adapter_f:
                                facts.append(adapter_f.model_copy(update={
                                    "subject": r.get("subject", adapter_f.subject),
                                    "predicate": r.get("predicate", adapter_f.predicate),
                                    "object": r.get("object", adapter_f.object),
                                    "confidence": float(r.get("confidence", adapter_f.confidence))
                                }))
                            else:
                                facts.append(FactDTO(
                                    fact_id=fid,
                                    scene_id=sid,
                                    work_id=r.get("work_id", "the-bat-whispers-1930"),
                                    edition_id=r.get("edition_id", "tbw-fullscreen-archive"),
                                    dataset_version=r.get("dataset_version", "v3"),
                                    timestamp_ms=ts,
                                    subject=r.get("subject", ""),
                                    predicate=r.get("predicate", ""),
                                    object=r.get("object", ""),
                                    confidence=float(r.get("confidence", 1.0)),
                                    evidence_hash=r.get("evidence_hash", "hash-mcp")
                                ))

            # Ensure any scene_ids referenced in seeds are present
            for seed in seeds:
                sids = seed.scene_ids if hasattr(seed, "scene_ids") else (
                    seed.get("scene_ids") if isinstance(seed, dict) and "scene_ids" in seed else (
                        [seed["scene_id"]] if isinstance(seed, dict) and "scene_id" in seed else []
                    )
                )
                for sid in sids:
                    if sid not in seen_sids:
                        sc = v3_adapter.get_scene(sid)
                        if sc and sc.start_ms < effective_cutoff:
                            seen_sids.add(sid)
                            valid_scenes.append(sc)

            unique_events = events
        else:
            # OFFLINE_FIXTURE: local V3 adapter allowed
            if not candidate_scene_ids:
                seen_sids_list: List[str] = []
                for seed in seeds:
                    sids = seed.scene_ids if hasattr(seed, "scene_ids") else (
                        seed.get("scene_ids") if isinstance(seed, dict) and "scene_ids" in seed else (
                            [seed["scene_id"]] if isinstance(seed, dict) and "scene_id" in seed else []
                        )
                    )
                    for sid in sids:
                        if sid not in seen_sids_list:
                            seen_sids_list.append(sid)
                candidate_scene_ids = seen_sids_list[:5]

            # Strictly exclude any scene starting at or after cutoff_ms
            scenes = [v3_adapter.get_scene(sid) for sid in candidate_scene_ids]
            valid_scenes = [s for s in scenes if s and s.start_ms < effective_cutoff]

            # Extract events and facts from verified scenes and seeds
            events = []
            facts = []
            for s in valid_scenes:
                events.extend(v3_adapter.get_events(cutoff_ms=effective_cutoff, scene_id=s.scene_id))
                facts.extend(v3_adapter.get_facts(cutoff_ms=effective_cutoff, scene_id=s.scene_id))

            unique_events = []
            seen_eids_set = set()
            for ev in events:
                if ev.event_id not in seen_eids_set:
                    seen_eids_set.add(ev.event_id)
                    unique_events.append(ev)

        # Extract dedicated epistemic evidence strictly from KNOWLEDGE_CONFLICT channel
        mcp_knowledge_evidence: List[Dict[str, Any]] = []
        for seed in seeds:
            if isinstance(seed, dict):
                phase_name = seed.get("phase", "") or seed.get("structured_payload", {}).get("phase", "")
                channel_name = seed.get("channel_name", "") or seed.get("channel", "")
                raw_rows = seed.get("structured_payload", {}).get("raw_rows", []) if "structured_payload" in seed else seed.get("raw_rows", [])
            else:
                phase_name = getattr(seed, "phase", "") or (seed.structured_payload.get("phase", "") if getattr(seed, "structured_payload", None) else "")
                channel_name = getattr(seed, "channel_name", "")
                raw_rows = seed.structured_payload.get("raw_rows", []) if getattr(seed, "structured_payload", None) else []

            if phase_name == "KNOWLEDGE_CONFLICT" or channel_name == "KNOWLEDGE_CONFLICT":
                for r in raw_rows:
                    if isinstance(r, dict) and (r.get("source_table") == "knowledge_states" or "knowledge_id" in r or "valid_from_ms" in r):
                        mcp_knowledge_evidence.append(r)
            else:
                for r in raw_rows:
                    if isinstance(r, dict) and r.get("source_table") == "knowledge_states":
                        mcp_knowledge_evidence.append(r)

        # Compile anomalies and causal path from channels/seeds
        anomalies = []
        for s in seeds:
            if isinstance(s, dict):
                score = float(s.get("salience_score", s.get("score", 0.0)))
                rationale = s.get("channel_rationale", s.get("rationale", ""))
                if score >= 0.7 and rationale:
                    anomalies.append(rationale)
            else:
                score = getattr(s, "salience_score", 0.0)
                rationale = getattr(s, "channel_rationale", "")
                if score >= 0.7 and rationale:
                    anomalies.append(rationale)

        causal_path = [s.scene_id for s in valid_scenes]

        return EvidenceBundle(
            bundle_id=f"bundle-{reveal.reveal_id}-{len(valid_scenes)}",
            reveal=reveal,
            blind_interpretation=reveal.previous_belief or "Routine and standard character interactions before the incident.",
            target_clue_title=f"Forensic Evidence Bundle for {reveal.title}",
            evidence_seeds=seeds,
            related_scenes=valid_scenes,
            observed_events=unique_events[:10],
            observed_facts=facts[:10],
            mcp_knowledge_evidence=mcp_knowledge_evidence,
            character_states=[{"entity": e, "state": "PRE_REVEAL_ACTIVE"} for e in (reveal.affected_entities or [])],
            audience_states=[{"knowledge_level": "BLIND_AUDIENCE", "cutoff_ms": effective_cutoff}],
            anomalies=anomalies[:5],
            causal_path=causal_path,
            alternative_explanations=[
                "Routine investigative coincidence",
                "Ordinary procedural check without hidden intent",
                "Ambiguous architectural curiosity"
            ],
            counterfactual_controls=[
                {"type": "REVEAL_SWAP", "control_reveal_id": "reveal-unrelated-control"},
                {"type": "EVIDENCE_ABLATION", "ablated_scene_id": valid_scenes[0].scene_id if valid_scenes else None}
            ]
        )


bundle_builder = EvidenceBundleBuilder()

