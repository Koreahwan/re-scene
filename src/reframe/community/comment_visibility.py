"""One fail-closed policy for list, detail and explicit comment unlocks."""

COMPLETED_INSPECTIONS = frozenset({'VERIFIED', 'AI_CLEAR', 'AI_SPOILER'})


def inspection_complete(status):
    return status in COMPLETED_INSPECTIONS


def comment_masked(comment, viewer, progress_locked, work_id=None, edition_id=None):
    if viewer.is_admin or (viewer.user_id == comment.author_id and not viewer.is_public_author):
        return False
    # Consent applies only to this comment version, never its parent or siblings.
    if f'COMMENT:{comment.id}:{comment.version_no}' in viewer.explicit_unlocks:
        return False
    if not inspection_complete(comment.inspection_status):
        return True
    cutoff_locked = bool(comment.author_cutoff_ms and
        viewer.work_progress_by_edition.get(f'{work_id}:{edition_id}', 0) < comment.author_cutoff_ms)
    return bool(progress_locked or cutoff_locked or comment.contains_spoilers or comment.inspection_status == 'AI_SPOILER')
