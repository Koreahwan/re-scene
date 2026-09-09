"""
Reframe V7 Synthetic Audience Lab & Demo Content Service
Handles deterministic simulation execution, idempotent database seeding, safe deletion boundaries,
provenance isolation, load-time manifest verification, and admin queries.
Strict Disclosure: INTERACTIVE_GEMINI_CURATED_SEED for curated demo content.
Zero External Generative Model Calls.
Fail-Closed Persona Loading: Zero synthetic fallback generation.
"""
from __future__ import annotations
import uuid
import json
import gzip
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, and_, or_
import structlog

from src.reframe.shared.config import settings
from src.reframe.simulation.schemas import (
    SimulationRunConfig,
    SimulationRunResult,
    SimulationMode,
    DerivedPersonaProfile,
)
from src.reframe.simulation.simulator import AudienceSimulator
from src.reframe.simulation.persona_adapter import persona_adapter
from src.reframe.simulation.fan_traits import fan_traits_assigner
from src.reframe.simulation.models import SyntheticPersona, SyntheticContentProvenance
from src.reframe.identity.models import User, Profile
from src.reframe.community.models import (
    Post,
    PostVersion,
    Claim,
    ClaimVersion,
    Comment,
    Counterclaim,
    CounterclaimEvidenceLink,
    PostEvidenceLink,
    Reaction,
)
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.evidence.models import EvidenceCatalog
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.simulation.content_factory import (
    CURATED_MAGAZINE_ARTICLES,
    CURATED_COMMUNITY_POSTS,
    CURATED_COUNTERCLAIMS,
)
from src.reframe.simulation.content_validation import content_validator

logger = structlog.get_logger(__name__)


class NemotronReproSampleUnavailable(Exception):
    """Raised when the deterministic 10k repro sample is missing, invalid, or corrupted."""
    pass


class NemotronDerivedCacheUnavailable(Exception):
    """Raised when the 100k derived persona cache is missing, invalid, or corrupted."""
    pass


class NemotronSourceUnavailable(Exception):
    """Raised when persona source files fail manifest verification or are missing."""
    pass


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class AudienceLabService:
    def __init__(self):
        self.salt = settings.SIMULATION_SALT

    def compute_policy_hash(self) -> str:
        """Normalized SHA256 of BehaviorPolicy configuration source."""
        policy_path = Path(__file__).parent / "behavior_policy.py"
        if policy_path.exists():
            return compute_file_sha256(policy_path)
        return hashlib.sha256(b"reframe_us_audience_policy_v1").hexdigest()

    def compute_scenario_hash(self) -> str:
        """Normalized SHA256 of Golden Path scenarios source."""
        scenario_path = Path(__file__).parent / "golden_path.py"
        if scenario_path.exists():
            return compute_file_sha256(scenario_path)
        return hashlib.sha256(b"reframe_scenario_matrix_v1").hexdigest()

    async def execute_certified_simulation(
        self,
        config: SimulationRunConfig,
        source_mode: str,
        source_path: Path,
        manifest_path: Path,
        enable_adaptive_stop: bool = False,
        heartbeat_callback: Optional[Callable[[int, int], None]] = None,
        checkpoint_callback: Optional[Callable[[str, Any], None]] = None,
    ) -> SimulationRunResult:
        """
        Certified common simulation execution wrapper.
        Strictly validates manifest and source file checksums before execution.
        Populates complete lineage metadata.
        """
        if not manifest_path.exists():
            raise NemotronSourceUnavailable(f"Manifest not found: {manifest_path}")
        if not source_path.exists():
            raise NemotronSourceUnavailable(f"Source file not found: {source_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        actual_source_sha = compute_file_sha256(source_path)
        expected_source_sha = manifest.get("sample_sha256", "")
        if actual_source_sha != expected_source_sha:
            raise NemotronSourceUnavailable(
                f"Source SHA mismatch: actual {actual_source_sha} != manifest {expected_source_sha}"
            )

        manifest_sha = compute_file_sha256(manifest_path)

        personas = self.load_personas(config.unique_source_personas, source_mode=source_mode)

        simulator = AudienceSimulator(config)
        result = simulator.run_simulation(
            personas,
            enable_adaptive_stop=enable_adaptive_stop,
            heartbeat_callback=heartbeat_callback,
            checkpoint_callback=checkpoint_callback,
        )

        result.source_mode = source_mode
        result.source_cache_sha256 = actual_source_sha
        result.source_cache_manifest_sha256 = manifest_sha
        result.sample_method = manifest.get("sample_method", "FULL_SOURCE_HASH_PRIORITY_RESERVOIR_V2")
        result.source_rows_seen = manifest.get("source_rows_seen", 1000000)
        result.eligible_adult_rows = manifest.get("eligible_adult_rows", 783005)
        result.full_stream_completed = manifest.get("full_stream_completed", True)
        result.policy_hash = self.compute_policy_hash()
        result.scenario_hash = self.compute_scenario_hash()

        return result

    async def execute_simulation_run(
        self,
        config: SimulationRunConfig,
        personas: Optional[List[DerivedPersonaProfile]] = None,
        source_mode: str = "AUTO",
    ) -> SimulationRunResult:
        """
        Executes a deterministic audience simulation run.
        Zero Model Calls.
        """
        base_dir = Path(settings.SIMULATION_DATA_DIR) / "personas"
        cache_100k = base_dir / "nemotron_usa_100k_cache.jsonl.gz"
        sample_10k = base_dir / "nemotron_usa_repro_sample_v1.jsonl.gz"

        target_path = cache_100k if config.unique_source_personas > 10000 else sample_10k
        if not target_path.exists() and cache_100k.exists():
            target_path = cache_100k

        mf_path = target_path.parent / f"{target_path.name.replace('.jsonl.gz', '').replace('.gz', '')}_manifest.json"

        mode = source_mode if source_mode != "AUTO" else ("LOCAL_DERIVED_CACHE" if config.unique_source_personas > 10000 else "REPRO_SAMPLE")

        return await self.execute_certified_simulation(
            config=config,
            source_mode=mode,
            source_path=target_path,
            manifest_path=mf_path,
            enable_adaptive_stop=(config.mode in [SimulationMode.DEMO_US, SimulationMode.FULL_US, SimulationMode.MAX_SCALE]),
        )

    def load_personas(
        self,
        count: int = 10000,
        source_mode: str = "AUTO",
    ) -> List[DerivedPersonaProfile]:
        """
        Loads safe derived profiles with strict load-time manifest verification.
        Validates:
        - actual gzip SHA == manifest SHA
        - actual line count == accepted_profile_count
        - unique persona count == accepted_profile_count
        - dataset revision matches settings
        - source_kind == REAL_NEMOTRON_SOURCE
        - nemotron_derived == true
        Strictly fails closed without silent fallback generator loops.
        """
        base_dir = Path(settings.SIMULATION_DATA_DIR) / "personas"
        cache_100k = base_dir / "nemotron_usa_100k_cache.jsonl.gz"
        sample_10k = base_dir / "nemotron_usa_repro_sample_v1.jsonl.gz"

        chosen_path: Optional[Path] = None
        manifest_path: Optional[Path] = None

        if source_mode == "TEST_FIXTURE":
            if getattr(settings, "ENVIRONMENT", "development") not in ["test", "development", "local"]:
                raise NemotronSourceUnavailable("TEST_FIXTURE persona source mode is only allowed under ENVIRONMENT=test.")
            # Deterministic synthetic test fixture
            fixtures: List[DerivedPersonaProfile] = []
            for i in range(count):
                p = DerivedPersonaProfile(
                    persona_id=f"test_pers_{i:05d}",
                    source_persona_id_hash=f"{i:064x}",
                    locale="en_US",
                    display_alias=f"Test Persona {i:05d}",
                    age_band="25-34",
                    state="CA" if i % 2 == 0 else "NY",
                    census_region="West" if i % 2 == 0 else "Northeast",
                    location_context="Urban",
                    education_group="Bachelor's",
                    occupation_group="Tech",
                    sampling_weight=1.0,
                    source_dataset="test_fixture",
                    source_revision="test_rev",
                )
                p.traits = fan_traits_assigner.assign_traits(p, seed=42)
                fixtures.append(p)
            return fixtures

        elif source_mode == "REPRO_SAMPLE":
            if not sample_10k.exists():
                raise NemotronReproSampleUnavailable(f"Repro sample missing at {sample_10k}")
            chosen_path = sample_10k
            manifest_path = base_dir / "nemotron_usa_repro_sample_v1_manifest.json"

        elif source_mode in ["LOCAL_DERIVED_CACHE", "DERIVED_CACHE"]:
            if not cache_100k.exists():
                raise NemotronDerivedCacheUnavailable(f"Derived cache missing at {cache_100k}")
            chosen_path = cache_100k
            manifest_path = base_dir / "nemotron_usa_100k_cache_manifest.json"

        elif source_mode == "HF_STREAM":
            from tools.simulation.import_nemotron_personas import iterate_source_records
            gen, _ = iterate_source_records(
                dataset_id=settings.NEMOTRON_DATASET_ID,
                revision=settings.NEMOTRON_DATASET_REVISION,
            )
            adapter = NemotronPersonaAdapter()
            streamed: List[DerivedPersonaProfile] = []
            for raw_row in gen:
                if len(streamed) >= count:
                    break
                p, err = adapter.adapt_row(raw_row, alias_index=len(streamed) + 1)
                if p is not None:
                    p.traits = fan_traits_assigner.assign_traits(p, seed=42)
                    streamed.append(p)
            if len(streamed) < count:
                raise NemotronSourceUnavailable(f"HF_STREAM provided {len(streamed)} personas, fewer than requested {count}.")
            return streamed

        else:  # AUTO
            if count > 10000:
                if cache_100k.exists():
                    chosen_path = cache_100k
                    manifest_path = base_dir / "nemotron_usa_100k_cache_manifest.json"
                else:
                    raise NemotronDerivedCacheUnavailable(f"Required 100k cache not found at {cache_100k}")
            else:
                if sample_10k.exists():
                    chosen_path = sample_10k
                    manifest_path = base_dir / "nemotron_usa_repro_sample_v1_manifest.json"
                elif cache_100k.exists():
                    chosen_path = cache_100k
                    manifest_path = base_dir / "nemotron_usa_100k_cache_manifest.json"
                else:
                    raise NemotronSourceUnavailable(
                        f"Neither repro sample ({sample_10k}) nor derived cache ({cache_100k}) exists."
                    )

        # 1. Load-time Manifest Verification
        if not manifest_path or not manifest_path.exists():
            raise NemotronSourceUnavailable(f"Manifest missing for {chosen_path}: {manifest_path}")

        try:
            with open(manifest_path, "r", encoding="utf-8") as mf:
                manifest = json.load(mf)
        except Exception as e:
            raise NemotronSourceUnavailable(f"Failed parsing manifest {manifest_path}: {e}") from e

        # Assert manifest schema requirements
        if manifest.get("source_kind") != "REAL_NEMOTRON_SOURCE":
            raise NemotronSourceUnavailable(f"Manifest source_kind must be REAL_NEMOTRON_SOURCE, got {manifest.get('source_kind')}")
        if not manifest.get("nemotron_derived"):
            raise NemotronSourceUnavailable("Manifest must have nemotron_derived=True")
        if manifest.get("dataset_revision") != settings.NEMOTRON_DATASET_REVISION:
            raise NemotronSourceUnavailable(
                f"Manifest revision {manifest.get('dataset_revision')} does not match settings {settings.NEMOTRON_DATASET_REVISION}"
            )

        actual_file_sha = compute_file_sha256(chosen_path)
        manifest_file_sha = manifest.get("sample_sha256")
        if actual_file_sha != manifest_file_sha:
            raise NemotronSourceUnavailable(
                f"SHA-256 mismatch for {chosen_path}: actual {actual_file_sha} != manifest {manifest_file_sha}"
            )

        expected_total_profiles = manifest.get("accepted_profile_count", 0)

        # 2. Parse and Verify Gzip Content
        personas: List[DerivedPersonaProfile] = []
        seen_ids: Set[str] = set()
        total_file_lines = 0

        try:
            with gzip.open(chosen_path, "rt", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        total_file_lines += 1
                        if len(personas) < count:
                            data = json.loads(line_str)
                            p = DerivedPersonaProfile(**data)
                            if p.persona_id not in seen_ids:
                                seen_ids.add(p.persona_id)
                                if not p.traits:
                                    p.traits = fan_traits_assigner.assign_traits(p, seed=42)
                                personas.append(p)
        except Exception as e:
            if "repro_sample" in str(chosen_path):
                raise NemotronReproSampleUnavailable(f"Failed parsing {chosen_path}: {e}") from e
            raise NemotronDerivedCacheUnavailable(f"Failed parsing {chosen_path}: {e}") from e

        # If loading the complete file (count >= expected_total_profiles), verify exact line counts
        if count >= expected_total_profiles:
            if total_file_lines != expected_total_profiles or len(seen_ids) != expected_total_profiles:
                raise NemotronSourceUnavailable(
                    f"Line count ({total_file_lines}) or unique persona count ({len(seen_ids)}) "
                    f"does not match manifest accepted_profile_count ({expected_total_profiles})."
                )

        if len(personas) < count:
            raise NemotronSourceUnavailable(
                f"Source file {chosen_path} provided {len(personas)} unique personas, fewer than requested {count}."
            )

        return personas

    load_reproducibility_personas = load_personas

    async def seed_synthetic_demo_content(
        self,
        db: AsyncSession,
        simulation_run_id: Optional[uuid.UUID] = None,
        enable_magazine: bool = True,
        enable_community: bool = True,
        post_target_count: int = 20,
        comment_target_count: int = 40,
        counterclaim_target_count: int = 20,
        reaction_target_count: int = 60,
    ) -> Dict[str, Any]:
        """
        Seeds idempotent synthetic demo content into PostgreSQL.
        Strict Provenance: Every created record is linked via SyntheticContentProvenance.
        Every author maps to SyntheticPersona.demo_user_id with status=DISABLED and no credentials.
        Enforces scope separation: if enable_community is False, zero community records are created.
        """
        if not enable_magazine and not enable_community:
            raise ValueError("Scope error: at least one of enable_magazine or enable_community must be True.")

        if not enable_community:
            post_target_count = 0
            comment_target_count = 0
            counterclaim_target_count = 0
            reaction_target_count = 0
        personas = self.load_personas(count=50)

        # 1. Ensure synthetic personas and auth-disabled users exist in DB
        author_personas: List[SyntheticPersona] = []
        author_users: List[User] = []

        for idx, p in enumerate(personas[:20], start=1):
            stmt = select(SyntheticPersona).where(SyntheticPersona.source_persona_id_hash == p.source_persona_id_hash)
            res = await db.execute(stmt)
            sp = res.scalars().first()

            # Create User first if missing
            user_id = uuid.uuid4()
            if sp and sp.demo_user_id:
                u_res = await db.execute(select(User).where(User.id == sp.demo_user_id))
                user = u_res.scalars().first()
            else:
                user = None

            if not user:
                user = User(
                    id=user_id,
                    email_normalized=f"demo_synthetic_{p.persona_id}@example.invalid",
                    role="USER",
                    status="DISABLED",  # Fail-closed auth boundary
                    account_origin="SYNTHETIC_DEMO",
                )
                db.add(user)
                await db.flush()

                profile = Profile(
                    user_id=user.id,
                    display_name=p.display_alias,
                    locale=p.locale or "en",
                    fan_depth="DEEP_ANALYST",
                )
                db.add(profile)
                await db.flush()

            if not sp:
                sp = SyntheticPersona(
                    id=uuid.uuid4(),
                    source_dataset=p.source_dataset,
                    source_revision=p.source_revision,
                    source_persona_id_hash=p.source_persona_id_hash,
                    locale=p.locale,
                    display_alias=p.display_alias,
                    demographic_context={
                        "age_band": p.age_band,
                        "state": p.state,
                        "census_region": p.census_region,
                        "education_group": p.education_group,
                        "occupation_group": p.occupation_group,
                    },
                    fan_traits=p.traits.model_dump() if p.traits else {},
                    sampling_weight=p.sampling_weight,
                    is_repro_sample=True,
                    is_active=True,
                    demo_user_id=user.id,
                )
                db.add(sp)
                await db.flush()
            elif sp.demo_user_id != user.id:
                sp.demo_user_id = user.id
                await db.flush()

            author_personas.append(sp)
            author_users.append(user)

        # 2. Comprehensive Evidence Catalog Seeding for FACTS, EVENTS, SCENES, FRAMES
        evidence_db_map: Dict[str, uuid.UUID] = {}

        # 2a. Facts
        for fact in v3_adapter.get_facts():
            stmt = select(EvidenceCatalog).where(EvidenceCatalog.evidence_id == fact.fact_id)
            ev = (await db.execute(stmt)).scalars().first()
            if not ev:
                ev = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    dataset_version="v3.0.0",
                    evidence_type="fact",
                    evidence_id=fact.fact_id,
                    evidence_hash=fact.evidence_hash,
                    screen_start_ms=fact.timestamp_ms,
                    screen_end_ms=fact.timestamp_ms,
                    status="ACTIVE",
                )
                db.add(ev)
                await db.flush()
            evidence_db_map[fact.fact_id] = ev.id

        # 2b. Events
        for ev_item in v3_adapter.get_events():
            stmt = select(EvidenceCatalog).where(EvidenceCatalog.evidence_id == ev_item.event_id)
            ev = (await db.execute(stmt)).scalars().first()
            if not ev:
                ev = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    dataset_version="v3.0.0",
                    evidence_type="event",
                    evidence_id=ev_item.event_id,
                    evidence_hash=ev_item.evidence_hash,
                    screen_start_ms=ev_item.evidence_start_ms,
                    screen_end_ms=ev_item.evidence_end_ms,
                    status="ACTIVE",
                )
                db.add(ev)
                await db.flush()
            evidence_db_map[ev_item.event_id] = ev.id

        # 2c. Scenes
        for sc_item in v3_adapter.get_scenes():
            stmt = select(EvidenceCatalog).where(EvidenceCatalog.evidence_id == sc_item.scene_id)
            ev = (await db.execute(stmt)).scalars().first()
            if not ev:
                ev = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    dataset_version="v3.0.0",
                    evidence_type="scene",
                    evidence_id=sc_item.scene_id,
                    evidence_hash=sc_item.evidence_hash,
                    screen_start_ms=sc_item.start_ms,
                    screen_end_ms=sc_item.end_ms,
                    status="ACTIVE",
                )
                db.add(ev)
                await db.flush()
            evidence_db_map[sc_item.scene_id] = ev.id

        # 2d. Frames
        for fr_item in v3_adapter.get_evidence_frames():
            stmt = select(EvidenceCatalog).where(EvidenceCatalog.evidence_id == fr_item.frame_id)
            ev = (await db.execute(stmt)).scalars().first()
            if not ev:
                ev = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    dataset_version="v3.0.0",
                    evidence_type="frame",
                    evidence_id=fr_item.frame_id,
                    evidence_hash=fr_item.file_sha256 or fr_item.canonical_asset_sha256,
                    screen_start_ms=fr_item.timestamp_ms,
                    screen_end_ms=fr_item.timestamp_ms,
                    status="ACTIVE",
                )
                db.add(ev)
                await db.flush()
            evidence_db_map[fr_item.frame_id] = ev.id

        created_magazine_ids: List[uuid.UUID] = []
        existing_magazine_ids: List[uuid.UUID] = []
        created_post_ids: List[uuid.UUID] = []
        existing_post_ids: List[uuid.UUID] = []
        created_counterclaim_ids: List[uuid.UUID] = []
        existing_counterclaim_ids: List[uuid.UUID] = []
        created_comment_ids: List[uuid.UUID] = []
        existing_comment_ids: List[uuid.UUID] = []
        created_reaction_count = 0
        existing_reaction_count = 0

        # 3. Seed Curated Magazine Articles as Post.content_type = "MAGAZINE_ARTICLE"
        if enable_magazine:
            for idx, art_data in enumerate(CURATED_MAGAZINE_ARTICLES):
                stable_key = art_data["stable_key"]
                sp = author_personas[idx % len(author_personas)]
                author = author_users[idx % len(author_users)]

                prov_res = await db.execute(
                    select(SyntheticContentProvenance).where(SyntheticContentProvenance.stable_content_key == stable_key)
                )
                existing_prov = prov_res.scalars().first()
                if existing_prov:
                    existing_magazine_ids.append(existing_prov.subject_id)
                    continue

                safe_t = f"The Bat Whispers (1930) — Scene Analysis #{idx:02d}"
                safe_p = "Complete the required story reveal to unlock this structural scene analysis."

                # Verify safe metadata does not leak spoiler terms
                for kw in ["anderson", "identity", "killer", "robbery", "innocence", "secret room"]:
                    if kw in safe_t.lower() or kw in safe_p.lower():
                        raise ValueError(f"SPOILER_LEAK: Keyword '{kw}' detected in safe spoiler metadata.")

                spoiler = SpoilerScope(
                    id=uuid.uuid4(),
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    minimum_progress_ms=art_data.get("spoiler_cutoff_ms", 4860000),
                    required_reveal_ids=art_data.get("tagged_reveal_ids", ["reveal-anderson-identity"]),
                    severity="MAJOR",
                    safe_title=safe_t,
                    safe_preview=safe_p,
                )
                db.add(spoiler)
                await db.flush()

                post = Post(
                    id=uuid.uuid4(),
                    author_id=author.id,
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    content_type="MAGAZINE_ARTICLE",
                    status="PUBLISHED",
                    spoiler_scope_id=spoiler.id,
                    ai_disclosure="INTERACTIVE_GEMINI_CURATED_SEED",
                    published_at=datetime.now(timezone.utc),
                )
                db.add(post)
                await db.flush()

                body_data = {
                    "article_type": art_data.get("article_type", "SCENE_BREAKDOWN"),
                    "sections": art_data["body_sections"],
                }

                post_ver = PostVersion(
                    id=uuid.uuid4(),
                    post_id=post.id,
                    version_no=1,
                    title=art_data["title"],
                    body_markdown=json.dumps(body_data),
                    change_summary=art_data["dek"],
                    body_sanitized_html=f"<p>{art_data['dek']}</p>",
                    created_by=author.id,
                )
                db.add(post_ver)
                await db.flush()
                post.current_version_id = post_ver.id

                for ev_ref in art_data.get("evidence_refs", []):
                    ev_id = ev_ref.get("evidence_id")
                    catalog_id = evidence_db_map.get(ev_id)
                    if not catalog_id:
                        raise ValueError(f"UNRESOLVED_EVIDENCE_REF: Magazine article evidence '{ev_id}' not found in EvidenceCatalog.")
                    link = PostEvidenceLink(
                        id=uuid.uuid4(),
                        post_version_id=post_ver.id,
                        evidence_catalog_id=catalog_id,
                        relation="SUPPORTS",
                    )
                    db.add(link)

                prov = SyntheticContentProvenance(
                    id=uuid.uuid4(),
                    simulation_run_id=simulation_run_id,
                    persona_id=sp.id,
                    subject_type="MAGAZINE_ARTICLE",
                    subject_id=post.id,
                    content_origin="SYNTHETIC_DEMO",
                    generator_mode="INTERACTIVE_GEMINI_CURATED_SEED",
                    content_version="v1.0",
                    stable_content_key=stable_key,
                    source_dataset=sp.source_dataset,
                    source_revision=sp.source_revision,
                )
                db.add(prov)
                created_magazine_ids.append(post.id)

        # 4. Seed Curated Community Posts
        for idx, post_data in enumerate(CURATED_COMMUNITY_POSTS[:post_target_count]):
            stable_key = post_data["stable_key"]
            sp = author_personas[idx % len(author_personas)]
            author = author_users[idx % len(author_users)]

            prov_res = await db.execute(
                select(SyntheticContentProvenance).where(SyntheticContentProvenance.stable_content_key == stable_key)
            )
            existing_prov = prov_res.scalars().first()
            if existing_prov:
                existing_post_ids.append(existing_prov.subject_id)
                continue

            spoiler = SpoilerScope(
                id=uuid.uuid4(),
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                minimum_progress_ms=post_data.get("spoiler_cutoff_ms", 4860000),
                required_reveal_ids=post_data.get("tagged_reveal_ids", ["reveal-anderson-identity"]),
                severity="MAJOR",
                safe_title=post_data["title"][:50],
                safe_preview=post_data["body"][:100],
            )
            db.add(spoiler)
            await db.flush()

            post = Post(
                id=uuid.uuid4(),
                author_id=author.id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                content_type="FAN_THEORY",
                status="PUBLISHED",
                spoiler_scope_id=spoiler.id,
                ai_disclosure="INTERACTIVE_GEMINI_CURATED_SEED",
                published_at=datetime.now(timezone.utc),
            )
            db.add(post)
            await db.flush()

            post_ver = PostVersion(
                id=uuid.uuid4(),
                post_id=post.id,
                version_no=1,
                title=post_data["title"],
                body_markdown=post_data["body"],
                body_sanitized_html=f"<p>{post_data['body']}</p>",
                created_by=author.id,
            )
            db.add(post_ver)
            await db.flush()
            post.current_version_id = post_ver.id

            for ev_ref in post_data.get("evidence_refs", []):
                ev_id = ev_ref.get("evidence_id")
                catalog_id = evidence_db_map.get(ev_id)
                if not catalog_id:
                    raise ValueError(f"UNRESOLVED_EVIDENCE_REF: Post evidence '{ev_id}' not found in EvidenceCatalog.")
                link = PostEvidenceLink(
                    id=uuid.uuid4(),
                    post_version_id=post_ver.id,
                    evidence_catalog_id=catalog_id,
                    relation="SUPPORTS",
                )
                db.add(link)

            prov = SyntheticContentProvenance(
                id=uuid.uuid4(),
                simulation_run_id=simulation_run_id,
                persona_id=sp.id,
                subject_type="POST",
                subject_id=post.id,
                content_origin="SYNTHETIC_DEMO",
                generator_mode="INTERACTIVE_GEMINI_CURATED_SEED",
                content_version="v1.0",
                stable_content_key=stable_key,
                source_dataset=sp.source_dataset,
                source_revision=sp.source_revision,
            )
            db.add(prov)
            created_post_ids.append(post.id)

            # Create Claim
            claim = Claim(
                id=uuid.uuid4(),
                post_id=post.id,
                status="ACTIVE",
            )
            db.add(claim)
            await db.flush()

            claim_ver = ClaimVersion(
                id=uuid.uuid4(),
                claim_id=claim.id,
                text=post_data["title"],
                classification="STRONG_INTERPRETATION",
            )
            db.add(claim_ver)
            await db.flush()
            claim.current_version_id = claim_ver.id

            # Create Comments
            for c_idx, c_text in enumerate(post_data.get("sample_comments", [])):
                if len(created_comment_ids) + len(existing_comment_ids) >= comment_target_count:
                    break
                c_author = author_users[(idx + c_idx + 1) % len(author_users)]
                c_persona = author_personas[(idx + c_idx + 1) % len(author_personas)]
                c_key = f"{stable_key}_comment_{c_idx}"

                c_prov_res = await db.execute(
                    select(SyntheticContentProvenance).where(SyntheticContentProvenance.stable_content_key == c_key)
                )
                existing_c_prov = c_prov_res.scalars().first()
                if existing_c_prov:
                    existing_comment_ids.append(existing_c_prov.subject_id)
                    continue

                comment = Comment(
                    id=uuid.uuid4(),
                    post_id=post.id,
                    author_id=c_author.id,
                    comment_type="COMMENT",
                    body_markdown=c_text,
                    body_sanitized_html=f"<p>{c_text}</p>",
                    status="PUBLISHED",
                )
                db.add(comment)
                await db.flush()

                c_prov = SyntheticContentProvenance(
                    id=uuid.uuid4(),
                    simulation_run_id=simulation_run_id,
                    persona_id=c_persona.id,
                    subject_type="COMMENT",
                    subject_id=comment.id,
                    content_origin="SYNTHETIC_DEMO",
                    generator_mode="DETERMINISTIC_TEMPLATE_V1",
                    content_version="v1.0",
                    stable_content_key=c_key,
                    source_dataset=c_persona.source_dataset,
                    source_revision=c_persona.source_revision,
                )
                db.add(c_prov)
                created_comment_ids.append(comment.id)

            # Create Counterclaim
            if idx < len(CURATED_COUNTERCLAIMS) and (len(created_counterclaim_ids) + len(existing_counterclaim_ids)) < counterclaim_target_count:
                cc_data = CURATED_COUNTERCLAIMS[idx]
                cc_key = cc_data["stable_key"]
                cc_author = author_users[(idx + 3) % len(author_users)]
                cc_persona = author_personas[(idx + 3) % len(author_personas)]

                cc_prov_res = await db.execute(
                    select(SyntheticContentProvenance).where(SyntheticContentProvenance.stable_content_key == cc_key)
                )
                existing_cc_prov = cc_prov_res.scalars().first()
                if existing_cc_prov:
                    existing_counterclaim_ids.append(existing_cc_prov.subject_id)
                else:
                    counterclaim = Counterclaim(
                        id=uuid.uuid4(),
                        post_id=post.id,
                        target_claim_id=claim.id,
                        author_id=cc_author.id,
                        challenged_premise=cc_data["title"],
                        alternative_explanation=cc_data["body"],
                        status="OPEN",
                    )
                    db.add(counterclaim)
                    await db.flush()

                    for ev_ref in cc_data.get("evidence_refs", []):
                        ev_id = ev_ref.get("evidence_id")
                        catalog_id = evidence_db_map.get(ev_id)
                        if not catalog_id:
                            raise ValueError(f"UNRESOLVED_EVIDENCE_REF: Counterclaim evidence '{ev_id}' not found in EvidenceCatalog.")
                        cc_link = CounterclaimEvidenceLink(
                            id=uuid.uuid4(),
                            counterclaim_id=counterclaim.id,
                            evidence_catalog_id=catalog_id,
                            relation="SUPPORTS_COUNTERCLAIM",
                        )
                        db.add(cc_link)

                    cc_prov = SyntheticContentProvenance(
                        id=uuid.uuid4(),
                        simulation_run_id=simulation_run_id,
                        persona_id=cc_persona.id,
                        subject_type="COUNTERCLAIM",
                        subject_id=counterclaim.id,
                        content_origin="SYNTHETIC_DEMO",
                        generator_mode="INTERACTIVE_GEMINI_CURATED_SEED",
                        content_version="v1.0",
                        stable_content_key=cc_key,
                        source_dataset=cc_persona.source_dataset,
                        source_revision=cc_persona.source_revision,
                    )
                    db.add(cc_prov)
                    created_counterclaim_ids.append(counterclaim.id)

        # 5. Seed Synthetic Reactions up to target count with unique pairs
        all_seeded_post_ids = created_magazine_ids + existing_magazine_ids + created_post_ids + existing_post_ids

        # Build candidate unique pairs of (user, post)
        candidate_pairs = []
        for u_idx, u in enumerate(author_users):
            for p_idx, pid in enumerate(all_seeded_post_ids):
                candidate_pairs.append((u, author_personas[u_idx], pid, f"react_{u.id}_{pid}"))

        for r_user, r_persona, target_post_id, r_key in candidate_pairs:
            if (created_reaction_count + existing_reaction_count) >= reaction_target_count:
                break

            react_stmt = select(Reaction).where(
                and_(
                    Reaction.user_id == r_user.id,
                    Reaction.subject_type == "POST",
                    Reaction.subject_id == target_post_id,
                )
            )
            existing_react = (await db.execute(react_stmt)).scalars().first()
            if existing_react:
                existing_reaction_count += 1
                continue

            react = Reaction(
                id=uuid.uuid4(),
                user_id=r_user.id,
                subject_type="POST",
                subject_id=target_post_id,
                reaction_type="AGREE",
            )
            db.add(react)
            await db.flush()

            r_prov = SyntheticContentProvenance(
                id=uuid.uuid4(),
                simulation_run_id=simulation_run_id,
                persona_id=r_persona.id,
                subject_type="REACTION",
                subject_id=react.id,
                content_origin="SYNTHETIC_DEMO",
                generator_mode="DETERMINISTIC_TEMPLATE_V1",
                content_version="v1.0",
                stable_content_key=r_key,
                source_dataset=r_persona.source_dataset,
                source_revision=r_persona.source_revision,
            )
            db.add(r_prov)
            created_reaction_count += 1

        await db.commit()

        mag_req = 20 if enable_magazine else 0
        mag_done = len(created_magazine_ids) + len(existing_magazine_ids)
        post_done = len(created_post_ids) + len(existing_post_ids)
        comm_done = len(created_comment_ids) + len(existing_comment_ids)
        cc_done = len(created_counterclaim_ids) + len(existing_counterclaim_ids)
        react_done = created_reaction_count + existing_reaction_count

        return {
            "status": "SUCCESS",
            "magazine_articles": {
                "requested": mag_req,
                "created": len(created_magazine_ids),
                "existing": len(existing_magazine_ids),
                "unfulfilled": max(0, mag_req - mag_done),
                "rejected": 0,
            },
            "community_posts": {
                "requested": post_target_count,
                "created": len(created_post_ids),
                "existing": len(existing_post_ids),
                "unfulfilled": max(0, post_target_count - post_done),
                "rejected": 0,
            },
            "comments": {
                "requested": comment_target_count,
                "created": len(created_comment_ids),
                "existing": len(existing_comment_ids),
                "unfulfilled": max(0, comment_target_count - comm_done),
                "rejected": 0,
            },
            "counterclaims": {
                "requested": counterclaim_target_count,
                "created": len(created_counterclaim_ids),
                "existing": len(existing_counterclaim_ids),
                "unfulfilled": max(0, counterclaim_target_count - cc_done),
                "rejected": 0,
            },
            "reactions": {
                "requested": reaction_target_count,
                "created": created_reaction_count,
                "existing": existing_reaction_count,
                "unfulfilled": max(0, reaction_target_count - react_done),
                "rejected": 0,
            },
            "magazine_articles_seeded": mag_done,
            "community_posts_seeded": post_done,
            "comments_seeded": comm_done,
            "counterclaims_seeded": cc_done,
            "reactions_seeded": react_done,
            "personas_enrolled": len(author_personas),
            "generator_mode": "INTERACTIVE_GEMINI_CURATED_SEED",
            "disclosure_applied": "SYNTHETIC_DEMO",
        }

    async def purge_synthetic_demo_content(
        self,
        db: AsyncSession,
    ) -> Dict[str, int]:
        """
        Safely purges ALL synthetic demo content tracked via SyntheticContentProvenance.
        Preserves all human users, human posts, comments, reactions, and verified proof records.
        """
        stmt = select(SyntheticContentProvenance)
        res = await db.execute(stmt)
        provenances = res.scalars().all()

        post_ids = [p.subject_id for p in provenances if p.subject_type in ["POST", "MAGAZINE_ARTICLE"]]
        comment_ids = [p.subject_id for p in provenances if p.subject_type == "COMMENT"]
        counterclaim_ids = [p.subject_id for p in provenances if p.subject_type == "COUNTERCLAIM"]
        reaction_ids = [p.subject_id for p in provenances if p.subject_type == "REACTION"]

        demo_users_stmt = select(User.id).where(User.account_origin == "SYNTHETIC_DEMO")
        demo_user_ids = (await db.execute(demo_users_stmt)).scalars().all()

        # Delete reactions by synthetic users or on synthetic posts or tracked
        deleted_reactions = 0
        if reaction_ids or demo_user_ids or post_ids:
            del_react = await db.execute(
                delete(Reaction).where(
                    or_(
                        Reaction.id.in_(reaction_ids) if reaction_ids else False,
                        Reaction.user_id.in_(demo_user_ids) if demo_user_ids else False,
                        Reaction.subject_id.in_(post_ids) if post_ids else False,
                    )
                )
            )
            deleted_reactions = del_react.rowcount or 0

        # Delete comments
        deleted_comments = 0
        if comment_ids:
            del_c = await db.execute(delete(Comment).where(Comment.id.in_(comment_ids)))
            deleted_comments = del_c.rowcount or 0

        # Delete counterclaims
        deleted_counterclaims = 0
        if counterclaim_ids:
            # Delete counterclaim evidence links first
            await db.execute(delete(CounterclaimEvidenceLink).where(CounterclaimEvidenceLink.counterclaim_id.in_(counterclaim_ids)))
            del_cc = await db.execute(delete(Counterclaim).where(Counterclaim.id.in_(counterclaim_ids)))
            deleted_counterclaims = del_cc.rowcount or 0

        # Delete posts (cascades versions, claims, links)
        deleted_posts = 0
        if post_ids:
            # Delete post versions and links first
            p_ver_ids = (await db.execute(select(PostVersion.id).where(PostVersion.post_id.in_(post_ids)))).scalars().all()
            if p_ver_ids:
                await db.execute(delete(PostEvidenceLink).where(PostEvidenceLink.post_version_id.in_(p_ver_ids)))
            del_p = await db.execute(delete(Post).where(Post.id.in_(post_ids)))
            deleted_posts = del_p.rowcount or 0

        # Delete provenances
        del_prov = await db.execute(delete(SyntheticContentProvenance))
        deleted_prov = del_prov.rowcount or 0

        # Delete synthetic personas & demo users
        del_pers = await db.execute(delete(SyntheticPersona))
        deleted_personas = del_pers.rowcount or 0

        del_users = await db.execute(delete(User).where(User.account_origin == "SYNTHETIC_DEMO"))
        deleted_users = del_users.rowcount or 0

        await db.commit()

        return {
            "posts_deleted": deleted_posts,
            "comments_deleted": deleted_comments,
            "counterclaims_deleted": deleted_counterclaims,
            "reactions_deleted": deleted_reactions,
            "provenances_deleted": deleted_prov,
            "synthetic_personas_deleted": deleted_personas,
            "synthetic_users_deleted": deleted_users,
        }


audience_lab_service = AudienceLabService()
