"""
Reframe V7 Community Service & Spoiler Scope Derivation
"""
import uuid
import html
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import structlog

from src.reframe.community.models import (
    Post, PostVersion, Claim, ClaimVersion, PostEvidenceLink,
    Counterclaim, CounterclaimEvidenceLink, Reaction, FilmReviewSlot
)
from src.reframe.evidence.models import EvidenceCatalog
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility
from src.reframe.identity.models import User, Profile
from src.reframe.identity.auth import ViewerContext
from src.reframe.audit.service import audit_service
from src.reframe.community.schemas import CreatePostRequest, CreateCounterclaimRequest
from src.reframe.shared.config import settings

logger = structlog.get_logger(__name__)



class CommunityService:
    @staticmethod
    async def claim_review_slot(db: AsyncSession, user_id: uuid.UUID, work_id: str, post_id: Optional[uuid.UUID] = None):
        """Serialize rated writes per account and film, including legacy post edits."""
        await db.execute(select(User.id).where(User.id == user_id).with_for_update())
        existing_query = select(Post.id).join(PostVersion, Post.current_version_id == PostVersion.id).where(
            Post.author_id == user_id, Post.work_id == work_id,
            Post.status != "REMOVED", PostVersion.rating.is_not(None))
        if post_id is not None:
            existing_query = existing_query.where(Post.id != post_id)
        if (await db.execute(existing_query.limit(1))).scalar_one_or_none():
            raise HTTPException(409, "You already reviewed this film. Use Edit My Review.")
        slot = (await db.execute(select(FilmReviewSlot).where(
            FilmReviewSlot.user_id == user_id, FilmReviewSlot.work_id == work_id
        ).with_for_update())).scalar_one_or_none()
        if slot is not None and slot.post_id is not None and slot.post_id != post_id:
            previous = await db.get(Post, slot.post_id)
            if previous and previous.status != "REMOVED":
                raise HTTPException(409, "You already reviewed this film. Use Edit My Review.")
        if slot is None:
            slot = FilmReviewSlot(user_id=user_id, work_id=work_id)
            db.add(slot)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(409, "A review is already being posted for this film. Refresh to edit it.")
        if post_id is not None:
            slot.post_id = post_id
        return slot

    @staticmethod
    async def create_post(
        db: AsyncSession,
        user_id: uuid.UUID,
        req: CreatePostRequest,
        commit: bool = True
    ) -> Post:
        """
        Creates a new community post with mandatory evidence verification and server-derived spoiler scope.
        """
        if not req.title.strip() or not req.body_markdown.strip():
            raise HTTPException(422, "A title and nonblank review are required")
        if req.content_type == "REVIEW" and req.rating is None:
            raise HTTPException(422, "Choose a rating before posting a review")
        review_slot = await CommunityService.claim_review_slot(db, user_id, req.work_id) if req.rating is not None else None
        # 1. Resolve and validate all evidence links against EvidenceCatalog
        resolved_catalog_ids: List[Tuple[uuid.UUID, int, str]] = []
        max_evidence_screen_ms = 0
        required_reveals = list(req.tagged_reveal_ids)

        for ev_input in req.evidence_links:
            ev_type = (ev_input.evidence_type or "").lower().strip()
            stmt = select(EvidenceCatalog).where(
                EvidenceCatalog.work_id == req.work_id,
                EvidenceCatalog.edition_id == req.edition_id,
                EvidenceCatalog.evidence_type == ev_type,
                EvidenceCatalog.evidence_id == ev_input.evidence_id
            )
            res = await db.execute(stmt)
            catalog_entry = res.scalars().first()

            # If not in DB, sync or retrieve from v3 adapter
            if not catalog_entry:
                ev_ref = v3_adapter.get_evidence_ref(ev_type, ev_input.evidence_id)
                if not ev_ref:
                    raise HTTPException(status_code=400, detail=f"Evidence ID '{ev_input.evidence_id}' not found in canonical catalog")
                
                # Create catalog entry on the fly
                ts_start = 0
                ts_end = 0
                if ev_type == "scene":
                    s = v3_adapter.get_scene(ev_input.evidence_id)
                    ts_start, ts_end = (s.start_ms, s.end_ms) if s else (0, 0)
                elif ev_type == "event":
                    e = v3_adapter.get_event(ev_input.evidence_id)
                    ts_start, ts_end = (e.evidence_start_ms, e.evidence_end_ms) if e else (0, 0)

                catalog_entry = EvidenceCatalog(
                    id=uuid.uuid4(),
                    work_id=req.work_id,
                    edition_id=req.edition_id,
                    dataset_version="v3",
                    evidence_type=ev_type,
                    evidence_id=ev_input.evidence_id,
                    evidence_hash=ev_ref.evidence_content_hash,
                    screen_start_ms=ts_start,
                    screen_end_ms=ts_end,
                    status="ACTIVE"
                )
                db.add(catalog_entry)
                await db.flush()

            resolved_catalog_ids.append((catalog_entry.id, catalog_entry.screen_end_ms, ev_input.relation))
            if catalog_entry.screen_end_ms > max_evidence_screen_ms:
                max_evidence_screen_ms = catalog_entry.screen_end_ms

        # 2. Derive minimum progress and spoiler scope server-side
        # If tagged reveals exist, incorporate their cutoff timestamps
        for rev_id in req.tagged_reveal_ids:
            rev = v3_adapter.get_reveal(rev_id)
            if rev and rev.timestamp_ms > max_evidence_screen_ms:
                max_evidence_screen_ms = rev.timestamp_ms

        if getattr(req, "author_cutoff_ms", None) is not None and req.author_cutoff_ms > max_evidence_screen_ms:
            max_evidence_screen_ms = req.author_cutoff_ms

        from src.reframe.narrative.blindness import blind_alias
        scope = SpoilerScope(
            id=uuid.uuid4(),
            work_id=req.work_id,
            edition_id=req.edition_id,
            minimum_progress_ms=max_evidence_screen_ms,
            required_reveal_ids=required_reveals,
            severity="ENDING" if max_evidence_screen_ms >= 4500000 else "MIDPOINT",
            safe_title=f"Fan Theory: {blind_alias.anonymize_text(req.title)[:40]}...",
            safe_preview="A fan theory analyzing narrative clues."
        )
        db.add(scope)
        await db.flush()

        # 3. Create Post record
        post_id = uuid.uuid4()
        post_version_id = uuid.uuid4()

        post = Post(
            id=post_id,
            author_id=user_id,
            work_id=req.work_id,
            edition_id=req.edition_id,
            content_type=req.content_type,
            current_version_id=post_version_id,
            status="PUBLISHED",
            spoiler_scope_id=scope.id,
            ai_disclosure=req.ai_disclosure,
            published_at=datetime.now(timezone.utc)
        )
        db.add(post)
        if review_slot is not None:
            # Flush the referenced post before assigning the slot's foreign key.
            await db.flush()
            review_slot.post_id = post.id

        # 4. Create PostVersion
        sanitized_html = f"<p>{html.escape(req.body_markdown)}</p>"
        post_version = PostVersion(
            id=post_version_id,
            post_id=post_id,
            version_no=1,
            title=req.title,
            body_markdown=req.body_markdown,
            body_sanitized_html=sanitized_html,
            created_by=user_id,
            rating=getattr(req, "rating", None),
            author_cutoff_ms=getattr(req, "author_cutoff_ms", None),
            contains_spoilers=req.contains_spoilers,
        )
        db.add(post_version)

        # 5. Create Claim & ClaimVersion if claim text provided
        claim_version_id = None
        if req.claim_text:
            claim_id = uuid.uuid4()
            claim_version_id = uuid.uuid4()
            claim = Claim(
                id=claim_id,
                post_id=post_id,
                current_version_id=claim_version_id,
                status="ACTIVE"
            )
            db.add(claim)

            claim_ver = ClaimVersion(
                id=claim_version_id,
                claim_id=claim_id,
                text=req.claim_text,
                classification=req.claim_classification or "STRONG_INTERPRETATION"
            )
            db.add(claim_ver)

        # 6. Link Evidence
        for cat_id, _, relation in resolved_catalog_ids:
            link = PostEvidenceLink(
                id=uuid.uuid4(),
                post_version_id=post_version_id,
                claim_version_id=claim_version_id,
                evidence_catalog_id=cat_id,
                relation=relation
            )
            db.add(link)

        # 6. Run spoiler inspection and apply conservative versioned inspection result
        from src.reframe.ai.inspection import spoiler_inspection_service
        insp_res = await spoiler_inspection_service.inspect_content(
            db=db,
            subject_id=post.id,
            version_no=1,
            raw_text=f"{req.title}\n{req.body_markdown}",
            user_cutoff_ms=max_evidence_screen_ms,
            work_id=req.work_id,
            edition_id=req.edition_id
        )
        await spoiler_inspection_service.apply_post_inspection_result(
            db=db,
            post_id=post.id,
            version_no=1,
            result=insp_res,
            user_cutoff_ms=max_evidence_screen_ms
        )

        # 7. Emit Audit Log & Outbox Event
        await audit_service.record_audit_log(
            db=db,
            actor_type="USER",
            actor_id=str(user_id),
            action="POST_CREATED",
            subject_type="post",
            subject_id=str(post_id),
            safe_metadata={"title": req.title[:64], "evidence_count": len(resolved_catalog_ids)}
        )
        await audit_service.emit_outbox_event(
            db=db,
            aggregate_type="post",
            aggregate_id=str(post_id),
            event_type="POST_PUBLISHED",
            payload={"post_id": str(post_id), "author_id": str(user_id)}
        )

        if commit:
            await db.commit()
        return post

    @staticmethod
    async def list_posts(
        db: AsyncSession,
        viewer: ViewerContext,
        work_id: str = "the-bat-whispers-1930",
        origin: Optional[str] = None,
        sort: Optional[str] = "recent",
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(Post, PostVersion, User, SpoilerScope, Profile)
            .join(PostVersion, Post.current_version_id == PostVersion.id)
            .join(User, Post.author_id == User.id)
            .outerjoin(Profile, User.id == Profile.user_id)
            .outerjoin(SpoilerScope, Post.spoiler_scope_id == SpoilerScope.id)
            .where(
                Post.work_id == work_id,
                Post.status == "PUBLISHED",
                Post.content_type.in_(["FAN_THEORY", "REVIEW"])
            )
        )
        if not settings.ENABLE_SYNTHETIC_DEMO_CONTENT:
            if origin and origin.upper() == "SYNTHETIC_DEMO" and not viewer.is_admin:
                return []
            stmt = stmt.where(User.account_origin.in_(["HUMAN", "SYSTEM", "PUBLIC_DEMO"]))
        elif origin and origin.upper() == "HUMAN":
            stmt = stmt.where(User.account_origin.in_(["HUMAN", "SYSTEM", "PUBLIC_DEMO"]))
        elif origin and origin.upper() == "SYNTHETIC_DEMO":
            stmt = stmt.where(User.account_origin == "SYNTHETIC_DEMO")

        stmt = stmt.order_by(Post.created_at.desc())

        res = await db.execute(stmt)
        rows = res.all()

        # Load reactions for listed posts
        post_ids = [p.id for p, _, _, _, _ in rows]
        like_counts: Dict[uuid.UUID, int] = {}
        viewer_liked_set: set[uuid.UUID] = set()
        if post_ids:
            rx_stmt = select(Reaction.subject_id, func.count(Reaction.id)).where(
                Reaction.subject_type == "POST",
                Reaction.reaction_type == "LIKE",
                Reaction.subject_id.in_(post_ids)
            ).group_by(Reaction.subject_id)
            rx_res = await db.execute(rx_stmt)
            like_counts = {p_id: count for p_id, count in rx_res.all()}

            if viewer.user_id:
                v_rx_stmt = select(Reaction.subject_id).where(
                    Reaction.subject_type == "POST",
                    Reaction.reaction_type == "LIKE",
                    Reaction.user_id == viewer.user_id,
                    Reaction.subject_id.in_(post_ids)
                )
                v_rx_res = await db.execute(v_rx_stmt)
                viewer_liked_set = set(v_rx_res.scalars().all())

        results = []
        for post, version, author, scope, profile in rows:
            content_ref = f"POST:{post.id}:{version.version_no}"
            visibility = evaluate_spoiler_visibility(scope, viewer, content_ref=content_ref)
            is_post_author = bool(viewer.user_id and post.author_id == viewer.user_id and not viewer.is_public_author)
            if is_post_author:
                visibility = SpoilerVisibility.VISIBLE
            is_post_unlocked = content_ref in viewer.explicit_unlocks
            insp_status = getattr(version, "inspection_status", "UNVERIFIED_CALLS_DISABLED")
            if version.contains_spoilers or insp_status in ("UNVERIFIED_CALLS_DISABLED", "UNVERIFIED_BUDGET_EXCEEDED", "UNVERIFIED_EVIDENCE_INSUFFICIENT", "FAILED"):
                # Invariant: Unverified content CANNOT be unmasked solely by watch progress!
                # Public visitors must confirm the warning for this specific content/version to view.
                if not is_post_author and not viewer.is_admin and not is_post_unlocked:
                    visibility = SpoilerVisibility.MASKED

            author_name = profile.display_name if profile and profile.display_name else (getattr(author, "email_normalized", "").split("@")[0] or "Anonymous")
            is_synthetic = author.account_origin == "SYNTHETIC_DEMO" or post.content_type == "MAGAZINE_ARTICLE"

            raw_payload = {
                "post_id": str(post.id),
                "work_id": post.work_id,
                "edition_id": post.edition_id,
                "content_type": post.content_type,
                "title": version.title,
                "body_markdown": version.body_markdown,
                "status": post.status,
                "author_name": author_name,
                "author_id": str(post.author_id),
                "can_edit": bool(viewer.is_authenticated and (is_post_author or viewer.is_admin)),
                "is_synthetic": is_synthetic,
                "content_origin": author.account_origin,
                "ai_disclosure": post.ai_disclosure,
                "version_no": version.version_no,
                "rating": version.rating,
                "author_cutoff_ms": version.author_cutoff_ms,
                "contains_spoilers": version.contains_spoilers,
                "inspection_status": insp_status,
                "like_count": like_counts.get(post.id, 0),
                "viewer_liked": post.id in viewer_liked_set,
                "created_at": post.created_at.isoformat()
            }
            sanitized = sanitize_payload_for_viewer(
                payload=raw_payload,
                visibility=visibility,
                safe_title=scope.safe_title if scope else "Protected Fan Post",
                safe_preview=scope.safe_preview if scope else "Spoiler-protected content"
            )
            results.append(sanitized)

        if sort == "popular":
            results.sort(
                key=lambda r: (
                    -r.get("like_count", 0),
                    -datetime.fromisoformat(r["created_at"]).timestamp(),
                    r["post_id"]
                )
            )
        else:
            results.sort(
                key=lambda r: (
                    -datetime.fromisoformat(r["created_at"]).timestamp(),
                    r["post_id"]
                )
            )

        return results


    @staticmethod
    async def get_post_detail(
        db: AsyncSession,
        post_id: uuid.UUID,
        viewer: ViewerContext
    ) -> Dict[str, Any]:
        stmt = (
            select(Post, PostVersion, User, SpoilerScope, Profile)
            .join(PostVersion, Post.current_version_id == PostVersion.id)
            .outerjoin(User, Post.author_id == User.id)
            .outerjoin(Profile, User.id == Profile.user_id)
            .outerjoin(SpoilerScope, Post.spoiler_scope_id == SpoilerScope.id)
            .where(Post.id == post_id)
        )
        res = await db.execute(stmt)
        row = res.one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")

        post, version, author, scope, profile = row
        # Publication status must strictly be checked FIRST before evaluating spoiler visibility.
        # Public readers (including public author, users with prior unlocks, or completed watch progress)
        # cannot access non-published posts. Only admin or private author previewing their own DRAFT.
        post_status = getattr(post, "status", "PUBLISHED")
        is_private_draft_preview = bool(
            post_status == "DRAFT"
            and viewer.user_id
            and getattr(post, "author_id", None) == viewer.user_id
            and not viewer.is_public_author
        )
        if post_status != "PUBLISHED" and not viewer.is_admin and not is_private_draft_preview:
            raise HTTPException(status_code=404, detail="Post not found")

        content_ref = f"POST:{post.id}:{version.version_no}"
        insp_status = getattr(version, "inspection_status", "UNVERIFIED_CALLS_DISABLED")
        is_post_author = bool(viewer.is_authenticated and post.author_id == viewer.user_id)
        if viewer.is_admin or is_private_draft_preview or is_post_author:
            visibility = SpoilerVisibility.VISIBLE
        else:
            visibility = evaluate_spoiler_visibility(scope, viewer, content_ref=content_ref)
            is_post_author = bool(viewer.user_id and post.author_id == viewer.user_id and not viewer.is_public_author)
            is_post_unlocked = content_ref in viewer.explicit_unlocks
            if version.contains_spoilers or insp_status in ("UNVERIFIED_CALLS_DISABLED", "UNVERIFIED_BUDGET_EXCEEDED", "UNVERIFIED_EVIDENCE_INSUFFICIENT", "FAILED"):
                # Invariant: Unverified content CANNOT be unmasked solely by watch progress!
                # Public visitors must confirm the warning for this specific content/version to view.
                if not is_post_author and not viewer.is_admin and not is_post_unlocked:
                    visibility = SpoilerVisibility.MASKED

        # Load evidence links
        links_stmt = (
            select(PostEvidenceLink, EvidenceCatalog)
            .join(EvidenceCatalog, PostEvidenceLink.evidence_catalog_id == EvidenceCatalog.id)
            .where(PostEvidenceLink.post_version_id == version.id)
        )
        links_res = await db.execute(links_stmt)
        links = [
            {
                "evidence_type": cat.evidence_type,
                "evidence_id": cat.evidence_id,
                "relation": l.relation
            }
            for l, cat in links_res.all()
        ]

        # Load counterclaims
        cc_stmt = (
            select(Counterclaim, User, Profile)
            .join(User, Counterclaim.author_id == User.id)
            .outerjoin(Profile, User.id == Profile.user_id)
            .where(Counterclaim.post_id == post.id)
        )
        cc_res = await db.execute(cc_stmt)
        counterclaims = []
        for cc, cc_author, cc_profile in cc_res.all():
            cc_name = cc_profile.display_name if cc_profile and cc_profile.display_name else (getattr(cc_author, "email_normalized", "").split("@")[0] or "Anonymous")

            # Load attached evidence links for this counterclaim (Task 10)
            from src.reframe.community.models import CounterclaimEvidenceLink
            ccl_stmt = (
                select(CounterclaimEvidenceLink, EvidenceCatalog)
                .join(EvidenceCatalog, CounterclaimEvidenceLink.evidence_catalog_id == EvidenceCatalog.id)
                .where(CounterclaimEvidenceLink.counterclaim_id == cc.id)
            )
            ccl_res = await db.execute(ccl_stmt)
            cc_links = [
                {
                    "evidence_type": cat.evidence_type,
                    "evidence_id": cat.evidence_id,
                    "evidence_hash": cat.evidence_hash
                }
                for _, cat in ccl_res.all()
            ]

            counterclaims.append({
                "counterclaim_id": str(cc.id),
                "author_name": cc_name,
                "challenged_premise": cc.challenged_premise,
                "alternative_explanation": cc.alternative_explanation,
                "evidence_links": cc_links,
                "status": cc.status
            })

        # Load claims
        claims_stmt = (
            select(Claim, ClaimVersion)
            .join(ClaimVersion, Claim.current_version_id == ClaimVersion.id)
            .where(Claim.post_id == post.id)
        )
        claims_res = await db.execute(claims_stmt)
        claims = [
            {
                "claim_id": str(c.id),
                "text": cv.text,
                "classification": cv.classification,
                "status": c.status
            }
            for c, cv in claims_res.all()
        ]

        # Load comments
        comments_list = await CommunityService.list_comments(db=db, post_id=post_id, viewer=viewer)

        # Load reaction counts
        rx_stmt = select(Reaction.reaction_type, func.count(Reaction.id)).where(
            Reaction.subject_type == "POST",
            Reaction.subject_id == post.id
        ).group_by(Reaction.reaction_type)
        rx_res = await db.execute(rx_stmt)
        reaction_counts = {r_type: count for r_type, count in rx_res.all()}

        viewer_liked = False
        if viewer.user_id:
            v_rx_stmt = select(Reaction.id).where(
                Reaction.subject_type == "POST",
                Reaction.reaction_type == "LIKE",
                Reaction.subject_id == post.id,
                Reaction.user_id == viewer.user_id
            ).limit(1)
            v_rx = (await db.execute(v_rx_stmt)).scalar_one_or_none()
            viewer_liked = v_rx is not None

        author_name = profile.display_name if profile and profile.display_name else (getattr(author, "email_normalized", "").split("@")[0] or "Anonymous")

        # A saved run stays attached to the original post and exact revision.
        # Only expose a public summary, never private run configuration or prompts.
        from src.reframe.jobs.models import AnalysisRun
        runs = (await db.execute(select(AnalysisRun).where(
            AnalysisRun.owner_user_id == post.author_id,
            AnalysisRun.run_type == "THEORY_VALIDATION",
        ).order_by(AnalysisRun.created_at.desc()))).scalars().all()
        validation_summary = None
        for run in runs:
            config = run.config_json or {}
            if config.get("theory_id") == str(post.id) and config.get("post_version_id") == str(version.id):
                result = run.result_json or {}
                mode = result.get("validation_mode", "LOCAL_KEYWORD_RETRIEVAL")
                verdict = result.get("validation_verdict", "PENDING")
                if mode == "LOCAL_KEYWORD_RETRIEVAL" and run.status == "COMPLETED":
                    verdict = "RELATED_EVIDENCE" if result.get("supporting_evidence") else "NO_MATCH"
                validation_summary = {"status": run.status,
                    "validation_verdict": verdict, "validation_mode": mode}
                break

        raw_payload = {
            "post_id": str(post.id),
            "validation_summary": validation_summary if visibility == SpoilerVisibility.VISIBLE else None,
            "work_id": post.work_id,
            "edition_id": post.edition_id,
            "content_type": post.content_type,
            "version_no": version.version_no,
            "rating": version.rating,
            "author_cutoff_ms": version.author_cutoff_ms,
            "contains_spoilers": version.contains_spoilers,
            "inspection_status": insp_status,
            "title": version.title,
            "body_markdown": version.body_markdown,
            "body_sanitized_html": version.body_sanitized_html,
            "status": post.status,
            "author_id": str(author.id),
            "author_name": author_name,
            "claims": claims,
            "evidence_links": links,
            "counterclaims": counterclaims,
            "comments": comments_list,
            "reactions_count": reaction_counts,
            "likes_count": reaction_counts.get("LIKE", 0),
            "like_count": reaction_counts.get("LIKE", 0),
            "viewer_liked": viewer_liked,
            "published_at": post.published_at.isoformat() if post.published_at else None

        }

        sanitized = sanitize_payload_for_viewer(
            payload=raw_payload,
            visibility=visibility,
            safe_title=scope.safe_title if scope else "Protected Fan Post",
            safe_preview=scope.safe_preview if scope else "Spoiler-protected content"
        )
        return sanitized

    @staticmethod
    async def create_counterclaim(
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        req: CreateCounterclaimRequest
    ) -> Counterclaim:
        # Verify target claim exists
        claim_stmt = select(Claim).where(Claim.id == req.target_claim_id, Claim.post_id == post_id)
        res = await db.execute(claim_stmt)
        claim = res.scalar_one_or_none()
        if not claim:
            raise HTTPException(status_code=404, detail="Target claim not found on post")

        cc = Counterclaim(
            id=uuid.uuid4(),
            post_id=post_id,
            target_claim_id=req.target_claim_id,
            author_id=user_id,
            challenged_premise=req.challenged_premise,
            alternative_explanation=req.alternative_explanation,
            status="OPEN"
        )
        db.add(cc)
        await db.flush()

        # Persist CounterclaimEvidenceLink if evidence_links are provided (Task 10)
        from src.reframe.community.models import CounterclaimEvidenceLink
        if req.evidence_links:
            post_stmt = select(Post).where(Post.id == post_id)
            post_res = await db.execute(post_stmt)
            post = post_res.scalar_one_or_none()
            work_id = post.work_id if post else "the-bat-whispers-1930"
            edition_id = post.edition_id if post else "tbw-fullscreen-archive"

            for ev_input in req.evidence_links:
                ev_type = (ev_input.evidence_type or "").lower().strip()
                stmt = select(EvidenceCatalog).where(
                    EvidenceCatalog.work_id == work_id,
                    EvidenceCatalog.edition_id == edition_id,
                    EvidenceCatalog.evidence_type == ev_type,
                    EvidenceCatalog.evidence_id == ev_input.evidence_id
                )
                res = await db.execute(stmt)
                catalog_entry = res.scalars().first()

                if not catalog_entry:
                    ev_ref = v3_adapter.get_evidence_ref(ev_type, ev_input.evidence_id)
                    if ev_ref:
                        ts_start = 0
                        ts_end = 0
                        if ev_type == "scene":
                            s = v3_adapter.get_scene(ev_input.evidence_id)
                            ts_start, ts_end = (s.start_ms, s.end_ms) if s else (0, 0)
                        elif ev_type == "event":
                            e = v3_adapter.get_event(ev_input.evidence_id)
                            ts_start, ts_end = (e.evidence_start_ms, e.evidence_end_ms) if e else (0, 0)

                        catalog_entry = EvidenceCatalog(
                            id=uuid.uuid4(),
                            work_id=work_id,
                            edition_id=edition_id,
                            dataset_version="v3",
                            evidence_type=ev_type,
                            evidence_id=ev_input.evidence_id,
                            evidence_hash=ev_ref.evidence_content_hash,
                            screen_start_ms=ts_start,
                            screen_end_ms=ts_end,
                            status="ACTIVE"
                        )
                        db.add(catalog_entry)
                        await db.flush()

                if catalog_entry:
                    ccl = CounterclaimEvidenceLink(
                        id=uuid.uuid4(),
                        counterclaim_id=cc.id,
                        evidence_catalog_id=catalog_entry.id
                    )
                    db.add(ccl)

        # Emit audit log
        await audit_service.record_audit_log(
            db=db,
            actor_type="USER",
            actor_id=str(user_id),
            action="COUNTERCLAIM_POSTED",
            subject_type="counterclaim",
            subject_id=str(cc.id),
            safe_metadata={"post_id": str(post_id)}
        )

        await db.commit()
        return cc

    @staticmethod
    async def add_reaction(
        db: AsyncSession,
        subject_type: str,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        reaction_type: str
    ) -> Reaction:
        stmt = select(Reaction).where(
            Reaction.subject_type == subject_type,
            Reaction.subject_id == subject_id,
            Reaction.user_id == user_id,
            Reaction.reaction_type == reaction_type
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            return existing

        reaction = Reaction(
            id=uuid.uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            user_id=user_id,
            reaction_type=reaction_type
        )
        db.add(reaction)
        await db.commit()
        return reaction

    @staticmethod
    async def delete_reaction(
        db: AsyncSession,
        subject_type: str,
        subject_id: uuid.UUID,
        user_id: uuid.UUID,
        reaction_type: str
    ) -> bool:
        stmt = select(Reaction).where(
            Reaction.subject_type == subject_type,
            Reaction.subject_id == subject_id,
            Reaction.user_id == user_id,
            Reaction.reaction_type == reaction_type
        )
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            await db.delete(existing)
            await db.commit()
            return True
        return False

    @staticmethod
    async def create_comment(
        db: AsyncSession,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        body_markdown: str,
        comment_type: str = "COMMENT",
        parent_comment_id: Optional[uuid.UUID] = None,
        author_cutoff_ms: Optional[int] = None,
        contains_spoilers: bool = False,
        commit: bool = True,
    ) -> Dict[str, Any]:
        from src.reframe.community.models import Comment
        # Validate post exists
        post_stmt = select(Post).where(Post.id == post_id)
        post = (await db.execute(post_stmt)).scalar_one_or_none()
        if not post or post.status != "PUBLISHED":
            raise HTTPException(status_code=404, detail="Post not found")

        if parent_comment_id:
            parent_stmt = select(Comment).where(Comment.id == parent_comment_id)
            parent_comment = (await db.execute(parent_stmt)).scalar_one_or_none()
            if not parent_comment or getattr(parent_comment, "status", "PUBLISHED") not in ("PUBLISHED", "DELETED"):
                raise HTTPException(status_code=400, detail="Parent comment not found")
            if parent_comment.post_id != post_id:
                raise HTTPException(status_code=400, detail="Parent comment belongs to a different post")
            if parent_comment.parent_comment_id is not None:
                raise HTTPException(status_code=400, detail="Replies cannot be nested more than 1 level deep")

        clean_body = body_markdown
        if not clean_body.strip():
            raise HTTPException(422, "A comment cannot be blank")
        comment = Comment(
            id=uuid.uuid4(),
            post_id=post_id,
            parent_comment_id=parent_comment_id,
            author_id=user_id,
            comment_type=comment_type,
            body_markdown=clean_body,
            body_sanitized_html=f"<p>{html.escape(clean_body)}</p>",
            spoiler_scope_id=post.spoiler_scope_id,
            author_cutoff_ms=author_cutoff_ms,
            contains_spoilers=contains_spoilers,
            version_no=1,
            inspection_status="UNVERIFIED_CALLS_DISABLED",
            status="PUBLISHED"
        )
        db.add(comment)
        await db.flush()

        # Determine parent post cutoff
        post_cutoff_ms = 0
        if post.spoiler_scope_id:
            parent_scope = (await db.execute(select(SpoilerScope).where(SpoilerScope.id == post.spoiler_scope_id))).scalar_one_or_none()
            if parent_scope:
                post_cutoff_ms = parent_scope.minimum_progress_ms or 0

        effective_cutoff_ms = max(post_cutoff_ms, author_cutoff_ms or 0)

        from src.reframe.community.comment_moderation import enqueue_comment
        enqueue_comment(db, comment)

        if commit:
            await db.commit()
        return {
            "comment_id": str(comment.id),
            "post_id": str(post_id),
            "author_id": str(user_id),
            "body_markdown": comment.body_markdown,
            "comment_type": comment.comment_type,
            "author_cutoff_ms": comment.author_cutoff_ms,
            "contains_spoilers": comment.contains_spoilers,
            "version_no": comment.version_no,
            "inspection_status": comment.inspection_status,
            "created_at": comment.created_at.isoformat()
        }

    @staticmethod
    async def list_comments(
        db: AsyncSession,
        post_id: uuid.UUID,
        viewer: ViewerContext
    ) -> List[Dict[str, Any]]:
        from src.reframe.community.models import Comment
        # 1. Fetch Post and verify parent publication status FIRST
        post_stmt = select(Post).where(Post.id == post_id)
        post = (await db.execute(post_stmt)).scalar_one_or_none()

        post_status = getattr(post, "status", "PUBLISHED") if post else None
        is_private_draft_preview = bool(
            post and post_status == "DRAFT"
            and viewer.user_id
            and getattr(post, "author_id", None) == viewer.user_id
            and not viewer.is_public_author
        )
        if not post or (post_status != "PUBLISHED" and not viewer.is_admin and not is_private_draft_preview):
            raise HTTPException(status_code=404, detail="Post not found")

        scope = None
        if post and getattr(post, "spoiler_scope_id", None):
            scope_stmt = select(SpoilerScope).where(SpoilerScope.id == post.spoiler_scope_id)
            scope = (await db.execute(scope_stmt)).scalar_one_or_none()

        stmt = select(Comment).where(Comment.post_id == post_id).order_by(Comment.created_at.asc())
        res = await db.execute(stmt)
        comments = res.scalars().all()
        profiles = (await db.execute(select(Profile).where(Profile.user_id.in_({c.author_id for c in comments})))).scalars().all() if comments else []
        author_names = {profile.user_id: profile.display_name for profile in profiles}

        comment_by_id = {c.id: c for c in comments}

        def is_ancestor_published(c_obj: Comment) -> bool:
            curr = c_obj
            while curr.parent_comment_id:
                parent = comment_by_id.get(curr.parent_comment_id)
                if not parent or getattr(parent, "status", "PUBLISHED") not in ("PUBLISHED", "DELETED"):
                    return False
                curr = parent
            return True

        valid_published_ids = {
            c.id for c in comments
            if getattr(c, "status", "PUBLISHED") == "PUBLISHED" and is_ancestor_published(c)
        }

        results = []
        for c in comments:
            c_status = getattr(c, "status", "PUBLISHED")
            if c_status == "DELETED":
                if any(reply.parent_comment_id == c.id and reply.id in valid_published_ids for reply in comments):
                    results.append({
                        "comment_id": str(c.id), "post_id": str(c.post_id),
                        "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
                        "author_id": None, "author_name": "", "status": "DELETED",
                        "body_markdown": "This comment has been deleted.",
                        "can_edit": False, "is_spoiler_masked": False,
                        "created_at": c.created_at.isoformat(), "version_no": c.version_no,
                    })
                continue
            # Filter non-published comments and any replies with non-published ancestors from public reads
            if not viewer.is_admin and (c_status != "PUBLISHED" or c.id not in valid_published_ids):
                continue

            c_version = getattr(c, "version_no", 1)
            comment_ref = f"COMMENT:{c.id}:{c_version}"
            comment_is_author = bool(viewer.user_id and c.author_id == viewer.user_id and not viewer.is_public_author)
            comment_unlocked = comment_ref in viewer.explicit_unlocks

            c_scope = scope
            if getattr(c, "spoiler_scope_id", None) and getattr(c, "spoiler_scope_id") != (scope.id if scope else None):
                c_scope_stmt = select(SpoilerScope).where(SpoilerScope.id == c.spoiler_scope_id)
                c_scope = (await db.execute(c_scope_stmt)).scalar_one_or_none() or scope

            if c_scope:
                # Content ref is None to evaluate watch progress and reveal checklist only,
                # preventing parent post explicit unlocks from exposing child comments.
                progress_visibility = evaluate_spoiler_visibility(c_scope, viewer, content_ref=None)
                is_locked = (progress_visibility in (SpoilerVisibility.LOCKED, SpoilerVisibility.MASKED)) and not comment_is_author and not viewer.is_admin
            else:
                is_locked = False

            insp_status = getattr(c, "inspection_status", "UNVERIFIED_CALLS_DISABLED")
            from src.reframe.community.comment_visibility import comment_masked
            if comment_masked(c, viewer, is_locked, post.work_id, post.edition_id):
                body = "🔒 [Spoiler Comment Masked] Complete the reveal or confirm warning to view."
                masked = True
            else:
                body = c.body_markdown
                masked = False

            results.append({
                "comment_id": str(c.id),
                "post_id": str(c.post_id),
                "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
                "author_id": str(c.author_id),
                "author_name": author_names.get(c.author_id, "Viewer"),
                "comment_type": c.comment_type,
                "body_markdown": body,
                "version_no": c_version,
                "author_cutoff_ms": getattr(c, "author_cutoff_ms", None),
                "contains_spoilers": c.contains_spoilers,
                "inspection_status": insp_status,
                "can_reveal": c_status == "PUBLISHED",
                "status": c_status,
                "is_spoiler_masked": masked,
                "visibility": SpoilerVisibility.MASKED if masked else SpoilerVisibility.VISIBLE,
                "can_edit": bool(viewer.is_authenticated and (viewer.is_admin or c.author_id == viewer.user_id)),
                "created_at": c.created_at.isoformat()
            })
        return results



    @staticmethod
    async def create_moderation_report(
        db: AsyncSession,
        reporter_id: uuid.UUID,
        subject_type: str,
        subject_id: uuid.UUID,
        category: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        from src.reframe.moderation.models import Report
        clean_desc = html.escape(description.strip()) if description else None
        report = Report(
            id=uuid.uuid4(),
            reporter_id=reporter_id,
            subject_type=subject_type,
            subject_id=subject_id,
            category=category,
            description=clean_desc,
            status="PENDING"
        )
        db.add(report)
        await db.commit()
        return {
            "report_id": str(report.id),
            "status": report.status,
            "category": report.category,
            "created_at": report.created_at.isoformat()
        }

    @staticmethod
    async def list_moderation_reports(
        db: AsyncSession,
        viewer: ViewerContext
    ) -> List[Dict[str, Any]]:
        from src.reframe.moderation.models import Report
        if not viewer.is_admin and not viewer.is_moderator:
            raise HTTPException(status_code=403, detail="Admin or moderator privileges required")
        stmt = select(Report).order_by(Report.created_at.desc())
        res = await db.execute(stmt)
        reports = res.scalars().all()
        return [
            {
                "report_id": str(r.id),
                "reporter_id": str(r.reporter_id),
                "subject_type": r.subject_type,
                "subject_id": str(r.subject_id),
                "category": r.category,
                "description": r.description,
                "status": r.status,
                "created_at": r.created_at.isoformat()
            }
            for r in reports
        ]


community_service = CommunityService()

