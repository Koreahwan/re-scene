"""
Reframe V7 Canonical Dataset Readiness & Evidence Integrity Diagnostic Engine.
Audits V3 baseline files, entity counts, referential integrity, and proof prerequisites
without executing paid model calls or modifying shared/production datastores.
Zero Paid Model Calls.
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple

APPROVED_DATASET_VERSIONS = {"v3", "the_bat_whispers_v3_gemini36"}
EXPECTED_CANONICAL_ASSET_SHA256 = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"


class DatasetReadinessDiagnostic:
    """
    Independent, executable validator of V3 dataset readiness for P0 Reframed Proofs.
    """
    def __init__(self, data_root: Optional[str] = None):
        self.repo_root = Path(__file__).parent.parent.parent.parent
        self.data_root = Path(data_root) if data_root else self.repo_root / "data"

        self.v3_export_path = self.data_root / "production" / "v3_dataset_export.json"
        self.reveals_registry_path = self.data_root / "production" / "reveals_registry.json"
        self.corrections_path = self.data_root / "production" / "canonical_corrections_v3.json"
        self.checkpoint_path = self.data_root / "manifests" / "preprocessing_checkpoint_v3_gemini36.json"
        self.frame_manifest_path = self.data_root / "manifests" / "v3_frame_manifest.json"
        self.gate4_doc_path = self.repo_root / "docs" / "operations" / "v7_p2_gate4_preflight_2026-09-04.md"

        self.target_reveals = [
            "reveal-anderson-identity",
            "reveal-secret-room-location"
        ]

    def _hash_file(self, path: Path) -> Tuple[str, int]:
        if not path.exists():
            return "FILE_NOT_FOUND", 0
        hasher = hashlib.sha256()
        total_bytes = 0
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
                total_bytes += len(chunk)
        return hasher.hexdigest(), total_bytes

    def audit_file_integrity(self) -> Dict[str, Any]:
        """Audits file existence, byte lengths, and SHA-256 hashes."""
        files = {
            "v3_dataset_export": self.v3_export_path,
            "reveals_registry": self.reveals_registry_path,
            "canonical_corrections_v3": self.corrections_path,
            "preprocessing_checkpoint_v3_gemini36": self.checkpoint_path,
            "v3_frame_manifest": self.frame_manifest_path,
            "v7_p2_gate4_preflight": self.gate4_doc_path
        }

        results = {}
        all_present = True
        for name, path in files.items():
            sha, size = self._hash_file(path)
            present = path.exists()
            if not present:
                all_present = False
            try:
                rel_path = str(path.relative_to(self.repo_root))
            except ValueError:
                rel_path = str(path)
            results[name] = {
                "path": rel_path,
                "exists": present,
                "size_bytes": size,
                "sha256": sha
            }

        return {
            "status": "PASS" if all_present else "FAIL",
            "files": results
        }

    def audit_entity_counts_and_baselines(self) -> Dict[str, Any]:
        """Validates 43 scenes / 187 events / 94 facts / 385 frames / 4 reveals baseline."""
        # Load export
        if not self.v3_export_path.exists():
            return {
                "status": "FAIL",
                "reason": "v3_dataset_export.json missing",
                "counts": {},
                "checks": {}
            }

        with open(self.v3_export_path, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        scenes = export_data.get("scenes", [])
        events = export_data.get("events", [])
        facts = export_data.get("facts", [])
        reveals = export_data.get("reveals", [])
        knowledge_states = export_data.get("knowledge_states", [])

        # Load frame manifest
        frames_list = []
        if self.frame_manifest_path.exists():
            with open(self.frame_manifest_path, "r", encoding="utf-8") as f:
                f_data = json.load(f)
                frames_list = f_data if isinstance(f_data, list) else f_data.get("frames", [])

        # Load checkpoint
        chk_chunks = {}
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                chk_data = json.load(f)
                chk_chunks = chk_data.get("processed_chunks", {})

        chk_events_count = sum(len(c.get("events", [])) for c in chk_chunks.values())
        chk_facts_count = sum(len(c.get("facts", [])) for c in chk_chunks.values())

        # Checkpoint events content comparison
        chk_events_by_id = {}
        for c in chk_chunks.values():
            for ev in c.get("events", []):
                chk_events_by_id[ev.get("event_id")] = ev

        events_content_match = (len(events) == chk_events_count)
        if events_content_match and chk_events_by_id:
            for ev in events:
                eid = ev.get("event_id")
                chk_ev = chk_events_by_id.get(eid)
                if not chk_ev:
                    events_content_match = False
                    break
                if (
                    ev.get("description") != chk_ev.get("description")
                    or ev.get("action") != chk_ev.get("action")
                    or ev.get("actor") != chk_ev.get("actor")
                    or ev.get("timestamp_ms") != chk_ev.get("timestamp_ms")
                ):
                    events_content_match = False
                    break

        # Load registry
        reg_reveals = []
        if self.reveals_registry_path.exists():
            with open(self.reveals_registry_path, "r", encoding="utf-8") as f:
                reg_reveals = json.load(f)

        # Dataset version validation
        root_ver = export_data.get("dataset_version")
        dataset_version_valid = (root_ver in APPROVED_DATASET_VERSIONS) and all(
            ev.get("dataset_version") in APPROVED_DATASET_VERSIONS for ev in events
        )

        # Baseline checks
        baseline_checks = {
            "scenes_count_43": len(scenes) == 43,
            "events_count_187": len(events) == 187,
            "facts_count_94": len(facts) == 94,
            "frames_count_385": len(frames_list) == 385,
            "registry_reveals_count_4": len(reg_reveals) == 4,
            "export_checkpoint_scenes_match": len(scenes) == len(chk_chunks),
            "export_checkpoint_events_match": events_content_match,
            "export_checkpoint_facts_match": len(facts) == chk_facts_count,
            "dataset_version_valid": dataset_version_valid,
        }

        all_baseline_passed = all(baseline_checks.values())

        return {
            "status": "PASS" if all_baseline_passed else "FAIL",
            "counts": {
                "scenes": len(scenes),
                "events": len(events),
                "facts": len(facts),
                "frames": len(frames_list),
                "export_reveals": len(reveals),
                "registry_reveals": len(reg_reveals),
                "knowledge_states": len(knowledge_states),
                "checkpoint_chunks": len(chk_chunks)
            },
            "checks": baseline_checks
        }

    def audit_referential_integrity(self) -> Dict[str, Any]:
        """Checks foreign keys, citations, duplicate IDs, asset hashes, and dataset versions."""
        if not self.v3_export_path.exists():
            return {
                "status": "FAIL",
                "unresolved_count": 1,
                "errors": ["Missing v3_dataset_export.json for referential integrity audit."]
            }

        with open(self.v3_export_path, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        frames_list = []
        if self.frame_manifest_path.exists():
            with open(self.frame_manifest_path, "r", encoding="utf-8") as f:
                f_data = json.load(f)
                frames_list = f_data if isinstance(f_data, list) else f_data.get("frames", [])

        reg_reveals = []
        if self.reveals_registry_path.exists():
            with open(self.reveals_registry_path, "r", encoding="utf-8") as f:
                reg_reveals = json.load(f)

        corrections = []
        if self.corrections_path.exists():
            with open(self.corrections_path, "r", encoding="utf-8") as f:
                corrections = json.load(f)

        errors = []

        raw_scenes = export_data.get("scenes", [])
        raw_events = export_data.get("events", [])
        raw_facts = export_data.get("facts", [])

        # Duplicate ID checks
        seen_scene_ids = set()
        for s in raw_scenes:
            sid = s.get("scene_id")
            if sid in seen_scene_ids:
                errors.append(f"Duplicate scene_id found: {sid}")
            seen_scene_ids.add(sid)

        seen_event_ids = set()
        for ev in raw_events:
            eid = ev.get("event_id")
            if eid in seen_event_ids:
                errors.append(f"Duplicate event_id found: {eid}")
            seen_event_ids.add(eid)

        seen_fact_ids = set()
        for fc in raw_facts:
            fid = fc.get("fact_id")
            if fid in seen_fact_ids:
                errors.append(f"Duplicate fact_id found: {fid}")
            seen_fact_ids.add(fid)

        # Dataset version checks
        root_ver = export_data.get("dataset_version")
        if root_ver not in APPROVED_DATASET_VERSIONS:
            errors.append(f"Unapproved root dataset_version: {root_ver}")
        for ev in raw_events:
            ev_ver = ev.get("dataset_version")
            if ev_ver not in APPROVED_DATASET_VERSIONS:
                errors.append(f"Event {ev.get('event_id')} has unapproved dataset_version: {ev_ver}")

        # Canonical asset sha256 check
        for r in reg_reveals:
            rid = r.get("reveal_id")
            asset_sha = r.get("canonical_asset_sha256")
            if asset_sha != EXPECTED_CANONICAL_ASSET_SHA256:
                errors.append(f"Reveal {rid} has invalid canonical_asset_sha256: {asset_sha} (expected {EXPECTED_CANONICAL_ASSET_SHA256})")

        scene_ids = seen_scene_ids
        event_ids = seen_event_ids
        fact_ids = seen_fact_ids
        frame_ids = {fm["frame_id"] for fm in frames_list}

        # 1. Events -> scene_id
        for ev in raw_events:
            if ev.get("scene_id") not in scene_ids:
                errors.append(f"Event {ev.get('event_id')} cites missing scene_id {ev.get('scene_id')}")
            for fid in ev.get("evidence_frame_ids", []):
                if fid not in frame_ids:
                    errors.append(f"Event {ev.get('event_id')} cites missing frame_id {fid}")

        # 2. Facts -> scene_id and frames
        for fc in raw_facts:
            if fc.get("scene_id") not in scene_ids:
                errors.append(f"Fact {fc.get('fact_id')} cites missing scene_id {fc.get('scene_id')}")
            for fid in fc.get("evidence_frame_ids", []):
                if fid not in frame_ids:
                    errors.append(f"Fact {fc.get('fact_id')} cites missing frame_id {fid}")

        # 3. Frames -> scene_id
        for fm in frames_list:
            sid = fm.get("scene_id")
            if sid and sid not in scene_ids:
                errors.append(f"Frame {fm.get('frame_id')} cites missing scene_id {sid}")

        # 4. Corrections -> target_id and scene_id
        for c in corrections:
            tid = c.get("target_id")
            sid = c.get("scene_id")
            if tid not in event_ids:
                errors.append(f"Correction target_id {tid} not found in events")
            if sid not in scene_ids:
                errors.append(f"Correction scene_id {sid} not found in scenes")

        # 5. Reveals -> evidence_scene_ids and validation_frame_ids
        for r in reg_reveals:
            rid = r.get("reveal_id")
            for sid in r.get("evidence_scene_ids", []):
                if sid not in scene_ids:
                    errors.append(f"Reveal {rid} cites missing evidence_scene_id {sid}")
            for fid in r.get("validation_frame_ids", []):
                if fid not in frame_ids:
                    errors.append(f"Reveal {rid} cites missing validation_frame_id {fid}")

        return {
            "status": "PASS" if not errors else "FAIL",
            "unresolved_count": len(errors),
            "errors": errors[:50]
        }

    def audit_proof_type_prerequisites(self) -> Dict[str, Any]:
        """
        Audits preconditions for the three P0 proof types across the two target reveals.
        Returns explicit readiness or concrete MISSING annotations required.
        """
        if not self.v3_export_path.exists() or not self.reveals_registry_path.exists():
            return {
                "status": "FAIL",
                "reason": "Missing required dataset files for proof type prerequisites audit.",
                "evaluations": {}
            }

        with open(self.v3_export_path, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        with open(self.reveals_registry_path, "r", encoding="utf-8") as f:
            reg_reveals = {r["reveal_id"]: r for r in json.load(f)}

        events = export_data.get("events", [])
        knowledge_states = export_data.get("knowledge_states", [])

        # Map knowledge states by entity
        ks_by_entity: Dict[str, List[Dict[str, Any]]] = {}
        for ks in knowledge_states:
            ent = ks.get("entity") or ks.get("subject", "UNKNOWN")
            ks_by_entity.setdefault(ent, []).append(ks)

        proof_evaluations = {}
        all_ready = True

        for rev_id in self.target_reveals:
            rev = reg_reveals.get(rev_id)
            if not rev:
                proof_evaluations[rev_id] = {"status": "FAIL", "reason": f"Reveal {rev_id} not in registry"}
                all_ready = False
                continue

            cutoff_ms = rev["timestamp_ms"]
            pre_cutoff_events = [ev for ev in events if ev.get("timestamp_ms", 0) < cutoff_ms]

            eval_res: Dict[str, Any] = {
                "reveal_id": rev_id,
                "title": rev["title"],
                "cutoff_ms": cutoff_ms,
                "proof_types": {}
            }

            # 1. KNOWLEDGE_LEAK prerequisites
            # Requires: Character epistemic state before broadcast timeline
            subject_char = rev.get("subject", "")
            matching_ks = ks_by_entity.get(subject_char, [])
            pre_cutoff_ks = [s for s in matching_ks if s.get("timestamp_ms", 0) < cutoff_ms]

            has_explicit_predicate = any(s.get("predicate") is not None for s in pre_cutoff_ks)
            if len(pre_cutoff_ks) == 0:
                kl_status = "MISSING"
                kl_note = f"Zero pre-cutoff knowledge states found for subject entity '{subject_char}' in dataset export."
                kl_needed = f"Requires annotating character perspective knowledge states for '{subject_char}' before {cutoff_ms}ms."
            elif not has_explicit_predicate:
                kl_status = "PARTIAL_INCOMPLETE"
                kl_note = f"Found {len(pre_cutoff_ks)} knowledge states for '{subject_char}', but all have predicate=None and lack formal proposition IDs."
                kl_needed = f"Requires standardizing knowledge_states table in ClickHouse with subject, predicate, object, and valid_from_ms."
            else:
                kl_status = "READY"
                kl_note = f"Found {len(pre_cutoff_ks)} validated knowledge states for '{subject_char}'."
                kl_needed = "None"

            eval_res["proof_types"]["KNOWLEDGE_LEAK"] = {
                "status": kl_status,
                "candidate_knowledge_states": len(pre_cutoff_ks),
                "assessment": kl_note,
                "missing_requirements": kl_needed
            }

            # 2. CLAIM_ACTION_CONFLICT prerequisites
            # Requires: Character spoken claim + contradictory physical action
            char_events = [ev for ev in pre_cutoff_events if subject_char.lower() in (ev.get("actor") or "").lower()]
            dialogue_actions = [ev for ev in char_events if any(kw in (ev.get("action") or "").lower() for kw in ["speak", "say", "state", "claim", "declare", "tell", "protest"])]
            physical_actions = [ev for ev in char_events if any(kw in (ev.get("action") or "").lower() for kw in ["inspect", "carry", "examine", "search", "enter", "touch", "operate"])]

            if len(dialogue_actions) > 0 and len(physical_actions) > 0:
                cac_status = "READY_POTENTIAL"
                cac_note = f"Found {len(dialogue_actions)} verbal events and {len(physical_actions)} physical events for '{subject_char}' pre-cutoff."
                cac_needed = "None for observation; requires Gemini ADK to ground verbal claim premise vs observable action premise."
            elif len(physical_actions) > 0:
                cac_status = "PARTIAL_ACTIONS_ONLY"
                cac_note = f"Found {len(physical_actions)} physical actions for '{subject_char}', but explicit verbal dialogue claim events are not separated."
                cac_needed = f"Dialogue lines in scene audio/captions need explicit claim proposition binding in event description or spoken_claim field."
            else:
                cac_status = "MISSING"
                cac_note = f"Insufficient actions for '{subject_char}' prior to cutoff."
                cac_needed = f"Observations for '{subject_char}' need event extraction in pre-cutoff scenes."

            eval_res["proof_types"]["CLAIM_ACTION_CONFLICT"] = {
                "status": cac_status,
                "dialogue_events_count": len(dialogue_actions),
                "physical_actions_count": len(physical_actions),
                "assessment": cac_note,
                "missing_requirements": cac_needed
            }

            # 3. HIDDEN_PLAN_CHAIN prerequisites
            # Requires: Multi-scene preparatory chain establishing premeditated action prior to reveal
            char_scenes = {ev.get("scene_id") for ev in char_events if ev.get("scene_id")}
            if len(char_scenes) >= 2:
                hpc_status = "READY"
                hpc_note = f"Character '{subject_char}' appears across {len(char_scenes)} distinct pre-cutoff scenes ({sorted(char_scenes)})."
                hpc_needed = "None for grounding; requires multi-step causal chain synthesis across scenes."
            else:
                hpc_status = "MISSING"
                hpc_note = f"Character '{subject_char}' appears in fewer than 2 pre-cutoff scenes ({len(char_scenes)})."
                hpc_needed = f"Requires at least 2 distinct pre-cutoff scenes with '{subject_char}' actions."

            eval_res["proof_types"]["HIDDEN_PLAN_CHAIN"] = {
                "status": hpc_status,
                "distinct_scenes_count": len(char_scenes),
                "assessment": hpc_note,
                "missing_requirements": hpc_needed
            }

            for pt_info in eval_res["proof_types"].values():
                if pt_info.get("status") in ("MISSING", "PARTIAL_INCOMPLETE", "PARTIAL_ACTIONS_ONLY"):
                    all_ready = False

            proof_evaluations[rev_id] = eval_res

        return {
            "status": "PASS" if all_ready else "FAIL",
            "evaluations": proof_evaluations
        }

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Runs full suite of data readiness diagnostics."""
        file_int = self.audit_file_integrity()
        baselines = self.audit_entity_counts_and_baselines()
        ref_int = self.audit_referential_integrity()
        proof_pre = self.audit_proof_type_prerequisites()

        overall_pass = (
            file_int["status"] == "PASS" and
            baselines["status"] == "PASS" and
            ref_int["status"] == "PASS" and
            proof_pre["status"] == "PASS"
        )

        return {
            "overall_status": "PASS" if overall_pass else "FAIL",
            "file_integrity": file_int,
            "entity_baselines": baselines,
            "referential_integrity": ref_int,
            "proof_type_prerequisites": proof_pre
        }


readiness_diagnostic = DatasetReadinessDiagnostic()
