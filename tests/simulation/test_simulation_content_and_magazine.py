"""
Reframe V7 Simulation Content & Magazine Unit Tests
Validates evidence grounding, spoiler cutoff derivation, magazine article structure, and rollback purge safety.
"""
import pytest
from src.reframe.simulation.content_factory import (
    CURATED_MAGAZINE_ARTICLES,
    CURATED_COMMUNITY_POSTS,
    CURATED_COUNTERCLAIMS,
)
from src.reframe.simulation.content_validation import content_validator


def test_magazine_articles_structure_and_grounding():
    assert len(CURATED_MAGAZINE_ARTICLES) >= 20

    for idx, art in enumerate(CURATED_MAGAZINE_ARTICLES):
        assert "stable_key" in art
        assert "title" in art
        assert "dek" in art
        assert "article_type" in art
        assert "spoiler_cutoff_ms" in art
        assert art["spoiler_cutoff_ms"] > 0
        assert "body_sections" in art

        sections = art["body_sections"]
        assert "WHAT_THE_FILM_SHOWS" in sections
        assert "CANONICAL_METADATA" in sections
        assert "ENGINE_INTERPRETATION" in sections
        assert "SYNTHETIC_AUTHOR_VIEW" in sections
        assert "ALTERNATIVE_EXPLANATION" in sections
        assert "REWATCH_TIMESTAMPS" in sections

        # Validate grounding against canonical evidence catalog
        is_grounded, err = content_validator.validate_content_grounding(
            timestamp_ms=art["spoiler_cutoff_ms"],
            trust_class=art.get("trust_class", "ENGINE_INFERENCE"),
        )
        assert is_grounded, f"Article {art['title']} failed grounding: {err}"


def test_community_posts_and_counterclaims():
    assert len(CURATED_COMMUNITY_POSTS) >= 20
    assert len(CURATED_COUNTERCLAIMS) >= 20

    for post in CURATED_COMMUNITY_POSTS:
        assert "title" in post
        assert "body" in post
        assert "cited_evidence" in post
        assert len(post["cited_evidence"]) >= 1

        is_grounded, err = content_validator.validate_content_grounding(
            trust_class="COMMUNITY_INTERPRETATION",
        )
        assert is_grounded, f"Post {post['title']} failed grounding: {err}"

    for cc in CURATED_COUNTERCLAIMS:
        assert "challenged_premise" in cc
        assert "alternative_explanation" in cc
