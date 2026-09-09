"""Analysis uses the current edition position, never retrospective knowledge flags."""
from src.reframe.spoiler.policy import SpoilerVisibility, evaluate_spoiler_visibility


# Only the three explicitly approved, edition-pinned film experiences change.
SEPARATED_ANALYSIS_EDITIONS = frozenset({
    ('the-bat-whispers-1930', 'tbw-fullscreen-archive'),
    ('the-greene-murder-case-1929', 'gmc-archive-1929'),
    ('the-thirteenth-chair-1929', 'ttc-archive-1929'),
})


def current_position(viewer, work_id, edition_id):
    value = viewer.work_progress_by_edition.get(f'{work_id}:{edition_id}', 0)
    # Invalid or missing positions fail closed, including NaN and bool.
    return value if type(value) is int and value >= 0 else 0


def analysis_visibility(scope, viewer):
    if (scope.work_id, scope.edition_id) not in SEPARATED_ANALYSIS_EDITIONS:
        return evaluate_spoiler_visibility(scope, viewer)
    progress = current_position(viewer, scope.work_id, scope.edition_id)
    cutoff = scope.minimum_progress_ms
    return (SpoilerVisibility.VISIBLE if type(cutoff) is int and cutoff >= 0
            and progress > 0 and progress >= cutoff else SpoilerVisibility.LOCKED)


def retrospective_cutoff(work_id, edition_id, reveal_cutoff_ms, runtime_ms):
    """Existing full-film syntheses have no audited, earlier knowledge bound.

    A scene timestamp or an early reveal does not bound the text, alternatives,
    premises, or later frames of such a synthesis. Preserve its full input bound.
    Separate segment-only observations have their own independently checked bound.
    """
    if (work_id, edition_id) not in SEPARATED_ANALYSIS_EDITIONS:
        return reveal_cutoff_ms
    if type(runtime_ms) is not int or runtime_ms <= 0:
        return 2**63 - 1
    return max(runtime_ms, reveal_cutoff_ms)
