"""
Unit Tests for Rewatch Page Grounding and Truthful Empty State
Zero Paid Model Calls ($0.00 spend).
"""
import re
from pathlib import Path


def test_rewatch_page_has_zero_hardcoded_fabricated_evidence():
    """
    Task 6 & 13: RewatchPage must not contain hardcoded fabricated narrative clue statements,
    hardcoded milestones array, or unconditional 'VERIFIED CANON' strings.
    """
    rewatch_file = Path("apps/web/src/pages/RewatchPage.tsx")
    assert rewatch_file.exists()

    content = rewatch_file.read_text(encoding="utf-8")

    # Forbidden fabricated clue strings
    forbidden_literals = [
        "Anderson diligently investigates",
        "Anderson is covertly checking escape routes",
        "Window Latch Inspection",
        "Perimeter Bypass",
        "Fireplace Lever Operation",
        "tbw-journey-01"
    ]

    for lit in forbidden_literals:
        assert lit not in content, f"Found hardcoded narrative clue in RewatchPage.tsx: '{lit}'"

    # Verify API evidence consumption and truthful empty state elements are present
    assert "apiClient.proof.getProofsForReveal" in content or "getProofsForReveal" in content
    assert ') : !activeProof || proofs.length === 0 ? (' in content
    assert 'data-testid="rewatch-empty-analysis"' in content
    assert "Interpretations for this reveal are not yet available" in content
    assert "const isVerifiedCanon = activeProof?.verification_status === 'VERIFIED_CANON'" in content
    assert "{isVerifiedCanon ? 'VERIFIED CANON' : 'Unverified interpretation'}" in content
