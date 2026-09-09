"""
Reframe V7 Central Spoiler Policy & Visibility Evaluation
"""
from typing import Optional, Dict, Any, List
import structlog

from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope

logger = structlog.get_logger(__name__)


class SpoilerVisibility:
    VISIBLE = "VISIBLE"
    MASKED = "MASKED"
    LOCKED = "LOCKED"


def evaluate_spoiler_visibility(
    scope: Optional[SpoilerScope],
    viewer: ViewerContext,
    content_ref: Optional[str] = None
) -> str:
    """
    Central deterministic evaluation of spoiler visibility according to spec 06 and Phase 1 rules.
    Returns: VISIBLE | MASKED | LOCKED
    """
    if scope is None:
        return SpoilerVisibility.VISIBLE

    # Admin override or full access role
    if viewer.is_admin or viewer.admin_override:
        return SpoilerVisibility.VISIBLE

    # User preferences: ALL spoilers allowed globally
    if viewer.spoiler_preferences.get("default_mode") == "ALL":
        return SpoilerVisibility.VISIBLE

    # Check explicit item/content unlock
    if content_ref and content_ref in viewer.explicit_unlocks:
        return SpoilerVisibility.VISIBLE
    scope_id_str = str(scope.id)
    if scope_id_str in viewer.explicit_unlocks:
        return SpoilerVisibility.VISIBLE

    # Work & edition progress lookup
    edition_key = f"{scope.work_id}:{scope.edition_id}"
    user_progress_ms = viewer.work_progress_by_edition.get(edition_key, 0)

    # Check progress requirement
    progress_satisfied = user_progress_ms >= scope.minimum_progress_ms

    # Check required reveals completed
    required_reveals = scope.required_reveal_ids if isinstance(scope.required_reveal_ids, list) else []
    reveals_satisfied = all(
        rev_id in viewer.completed_reveal_ids for rev_id in required_reveals
    )

    if progress_satisfied or (required_reveals and reveals_satisfied):
        return SpoilerVisibility.VISIBLE

    # Determine whether MASKED (warning banner with click-to-reveal) or LOCKED
    if content_ref or viewer.spoiler_preferences.get("default_mode") == "ASK":
        return SpoilerVisibility.MASKED

    return SpoilerVisibility.LOCKED


def sanitize_payload_for_viewer(
    payload: Dict[str, Any],
    visibility: str,
    safe_title: Optional[str] = None,
    safe_preview: Optional[str] = None,
    unlock_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Transforms a content dictionary into a spoiler-safe DTO according to its visibility.
    LOCKED: Returns only generic permitted metadata, completely stripping raw spoiler data.
    MASKED: Returns only safe title/preview plus unlock metadata. Never attaches raw payload.
    VISIBLE: Returns full payload.
    """
    if visibility == SpoilerVisibility.VISIBLE:
        res = dict(payload)
        res["visibility"] = SpoilerVisibility.VISIBLE
        res["is_spoiler_masked"] = False
        return res

    # Generic identifier and non-spoiler metadata preserved across locked/masked states
    safe_dto: Dict[str, Any] = {
        "visibility": visibility,
        "is_locked": True,
        "is_spoiler_masked": True,
        "safe_preview": {
            "title": safe_title or "Spoiler-protected content",
            "summary": safe_preview or "Content hidden behind spoiler protection. Complete the required reveal to unlock."
        }
    }

    # Retain non-spoiler entity identifiers and engagement metadata if present
    for key in [
        "id", "moment_id", "proof_id", "post_id", "reveal_id", "work_id",
        "movie_id", "edition_id", "scene_id", "created_at", "published_at", "status",
        "proof_type", "severity", "reaction_counts", "reply_count",
        "like_count", "likes_count", "viewer_liked", "version_no",
        "content_type", "author_name", "author_id", "can_edit", "rating", "author_cutoff_ms",
        "human_review_status", "live_analysis_pending_approval", "trust_namespace"
    ]:
        if key in payload:
            safe_dto[key] = payload[key]

    safe_dto["title"] = safe_title or "Spoiler-protected content"

    if unlock_metadata:
        safe_dto["unlock_metadata"] = unlock_metadata

    return safe_dto

