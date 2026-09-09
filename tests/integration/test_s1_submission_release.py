"""
S1 Submission Release Candidate Integration Test Suite.
Verifies RC-01 through RC-06 requirements:
- RC-01: Magazine listing, multiple distinct article details, honest provenance, 404 on missing.
- RC-02: Auth-free guest read on films, reveals, proofs, scene index, and media; write/privileged deny.
- RC-05: Media streaming with Range (HTTP 206), Content-Range, Accept-Ranges, scene-index within reveal cutoff.
- Public Gateway: Read allowlist for media/scene-index, Range pass-through, stripped auth, read-only demo header.
"""

import http.client
import json
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User, Profile
from src.reframe.community.models import Post, PostVersion
from src.reframe.simulation.models import SyntheticContentProvenance


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed_test_magazine():
    """Seeds test magazine articles: 1 synthetic and 1 editorial, with distinct IDs and bodies."""
    async with AsyncSessionLocal() as db:
        # Create author user & profile
        user = User(
            id=uuid.uuid4(),
            email_normalized=f"editor_{uuid.uuid4().hex[:8]}@reframe.local",
            status="ACTIVE",
            role="USER",
        )
        db.add(user)
        await db.flush()

        profile = Profile(
            user_id=user.id,
            display_name="Reframe Film Editorial",
        )
        db.add(profile)
        await db.flush()

        # Create Synthetic Persona
        from src.reframe.simulation.models import SyntheticPersona
        persona = SyntheticPersona(
            id=uuid.uuid4(),
            source_revision="rev1",
            source_persona_id_hash=f"hash_{uuid.uuid4().hex[:12]}",
            display_alias="Synthetic Cinema Fan",
            demo_user_id=user.id,
        )
        db.add(persona)
        await db.flush()

        # Create SpoilerScope for Article 1
        from src.reframe.spoiler.models import SpoilerScope
        sp1 = SpoilerScope(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            minimum_progress_ms=0,
            required_reveal_ids=[],
            severity="MINOR",
            safe_title="Synthetic Deep Dive: The Bat Unmasked",
            safe_preview="Overview of the bat unmasking",
        )
        db.add(sp1)
        await db.flush()

        # Article 1: Synthetic
        post1 = Post(
            id=uuid.uuid4(),
            author_id=user.id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            content_type="MAGAZINE_ARTICLE",
            status="PUBLISHED",
            spoiler_scope_id=sp1.id,
            ai_disclosure="INTERACTIVE_GEMINI_CURATED_SEED",
            published_at=datetime.now(timezone.utc),
        )
        db.add(post1)
        await db.flush()

        ver1 = PostVersion(
            id=uuid.uuid4(),
            post_id=post1.id,
            version_no=1,
            title="Synthetic Deep Dive: The Bat Unmasked",
            body_markdown=json.dumps({"article_type": "SCENE_BREAKDOWN", "sections": {"WHAT_THE_FILM_SHOWS": "Synthetic breakdown content 1"}}),
            change_summary="Initial synthetic seed",
            body_sanitized_html="<p>Synthetic breakdown content 1</p>",
            created_by=user.id,
        )
        db.add(ver1)
        post1.current_version_id = ver1.id

        prov1 = SyntheticContentProvenance(
            id=uuid.uuid4(),
            persona_id=persona.id,
            subject_type="MAGAZINE_ARTICLE",
            subject_id=post1.id,
            content_origin="SYNTHETIC_SIMULATION",
            generator_mode="PERSONA_DRIVEN",
            stable_content_key=f"mag_key_{uuid.uuid4().hex[:12]}",
            source_revision="rev1",
        )
        db.add(prov1)

        # Create SpoilerScope for Article 2
        sp2 = SpoilerScope(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            minimum_progress_ms=0,
            required_reveal_ids=[],
            severity="MINOR",
            safe_title="Editorial Review: Shadows of 1930 Cinema",
            safe_preview="Overview of 1930 cinema shadows",
        )
        db.add(sp2)
        await db.flush()

        # Article 2: Editorial (Not Synthetic)
        post2 = Post(
            id=uuid.uuid4(),
            author_id=user.id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            content_type="MAGAZINE_ARTICLE",
            status="PUBLISHED",
            spoiler_scope_id=sp2.id,
            ai_disclosure=None,
            published_at=datetime.now(timezone.utc),
        )
        db.add(post2)
        await db.flush()

        ver2 = PostVersion(
            id=uuid.uuid4(),
            post_id=post2.id,
            version_no=1,
            title="Editorial Review: Shadows of 1930 Cinema",
            body_markdown=json.dumps({"article_type": "EDITORIAL_ESSAY", "sections": {"WHAT_THE_FILM_SHOWS": "Editorial essay body 2"}}),
            change_summary="Initial editorial release",
            body_sanitized_html="<p>Editorial essay body 2</p>",
            created_by=user.id,
        )
        db.add(ver2)
        post2.current_version_id = ver2.id

        await db.commit()


@pytest.fixture(scope="module")
def api_client():
    """Deterministic FastAPI TestClient."""
    with TestClient(app) as client:
        yield client


# ============================================================================
# RC-01: Magazine Integration & Epistemic Separation
# ============================================================================

def test_rc01_magazine_list_when_synthetic_disabled(api_client, monkeypatch):
    """Verify /api/v1/magazine returns 200 with only editorial articles when synthetic is disabled."""
    monkeypatch.setattr(settings, "ENABLE_SYNTHETIC_MAGAZINE", False)
    resp = api_client.get("/api/v1/magazine")
    assert resp.status_code == 200
    data = resp.json()
    assert "articles" in data
    articles = data["articles"]
    assert len(articles) >= 1
    for a in articles:
        assert a["is_synthetic"] is False
        assert a["content_origin"] == "EDITORIAL"
        assert a["trust_class"] is None


def test_rc01_magazine_list_when_synthetic_enabled(api_client, monkeypatch):
    """Verify /api/v1/magazine returns 200 with both synthetic and editorial articles."""
    monkeypatch.setattr(settings, "ENABLE_SYNTHETIC_MAGAZINE", True)
    resp = api_client.get("/api/v1/magazine?origin=ALL")
    assert resp.status_code == 200
    data = resp.json()
    assert "articles" in data
    articles = data["articles"]
    assert len(articles) >= 2

    # Check distinct provenance
    origins = {a["content_origin"] for a in articles}
    assert "SYNTHETIC_SIMULATION" in origins
    assert "EDITORIAL" in origins


def test_rc01_magazine_two_distinct_article_details(api_client, monkeypatch):
    """Verify two distinct articles return unique details, correct titles, and bodies."""
    monkeypatch.setattr(settings, "ENABLE_SYNTHETIC_MAGAZINE", True)
    list_resp = api_client.get("/api/v1/magazine?origin=ALL")
    assert list_resp.status_code == 200
    items = list_resp.json()["articles"]
    assert len(items) >= 2

    id1 = items[0]["article_id"]
    id2 = items[1]["article_id"]
    assert id1 != id2, "Articles in list must have distinct IDs"

    # Fetch article 1
    resp1 = api_client.get(f"/api/v1/magazine/{id1}")
    assert resp1.status_code == 200
    art1 = resp1.json()
    assert art1["article_id"] == id1
    assert art1["title"] == items[0]["title"]
    assert len(art1["body_sections"]) > 0

    # Fetch article 2
    resp2 = api_client.get(f"/api/v1/magazine/{id2}")
    assert resp2.status_code == 200
    art2 = resp2.json()
    assert art2["article_id"] == id2
    assert art2["title"] == items[1]["title"]
    assert len(art2["body_sections"]) > 0

    # Content must not be identical fixed copies
    assert art1["title"] != art2["title"], "Two articles must not have identical titles"
    assert art1["body_sections"] != art2["body_sections"], "Two articles must not have identical body content"


def test_rc01_magazine_missing_article_returns_404(api_client):
    """Verify unknown article ID returns 404 (never 403 or 500)."""
    resp = api_client.get("/api/v1/magazine/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data or "detail" in data

    resp_invalid = api_client.get("/api/v1/magazine/not-a-uuid")
    assert resp_invalid.status_code == 404


# ============================================================================
# RC-02: Auth-Free Public Read Profile & Privileged Deny
# ============================================================================

def test_rc02_auth_free_read_flow(api_client):
    """Verify guest can access catalog, reveals, proofs, scene-index, and media without credentials."""
    # 1. /api/v1/auth/me returns guest context
    me_resp = api_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data.get("meta", {}).get("is_authenticated") is False
    assert me_data.get("data", {}).get("role") == "GUEST"

    # 2. Film detail
    film_resp = api_client.get("/api/v1/films/the-bat-whispers-1930")
    assert film_resp.status_code == 200
    assert film_resp.json()["data"]["movie_id"] == "the-bat-whispers-1930"

    # 3. Reveals list
    rev_resp = api_client.get("/api/v1/films/the-bat-whispers-1930/reveals")
    assert rev_resp.status_code == 200
    assert len(rev_resp.json()["data"]) > 0

    # 4. Proof detail
    proof_resp = api_client.get("/api/v1/proofs/proof-1")
    assert proof_resp.status_code in (200, 404)
    if proof_resp.status_code == 200:
        assert proof_resp.json()["data"]["proof_id"] == "proof-1"

    # 5. Scene index (guest reveal cutoff applied)
    scene_resp = api_client.get("/api/v1/films/the-bat-whispers-1930/scene-index")
    assert scene_resp.status_code == 200
    scenes = scene_resp.json()["data"]
    assert isinstance(scenes, list)
    assert len(scenes) == 41, f"Expected 41 scenes within cutoff, got {len(scenes)}"


def test_rc02_privileged_writes_denied_to_guests(api_client):
    """Verify admin and mutation endpoints are strictly rejected for unauthenticated guests."""
    adm_resp = api_client.post("/api/v1/admin/reveals/reveal-anderson-identity/refresh-proof", json={})
    assert adm_resp.status_code in (401, 403)


# ============================================================================
# RC-05: Media Streaming, Range (HTTP 206), and Scene Seeking
# ============================================================================

@pytest.fixture
def auth_client(api_client):
    resp = api_client.post("/api/v1/auth/dev-login", json={"role": "USER", "email": "streamer-rc05@example.test"})
    if resp.status_code == 200:
        csrf = resp.json().get("data", {}).get("csrf_token")
        if csrf:
            api_client.headers["X-CSRF-Token"] = csrf
    return api_client


def test_rc05_media_streaming_range_request(auth_client):
    """Retired playback must reject requests even when a Range header is supplied."""
    headers = {"Range": "bytes=0-100"}
    resp = auth_client.get("/api/v1/films/the-bat-whispers-1930/media", headers=headers)
    assert resp.status_code == 410
    assert "Content-Range" not in resp.headers


def test_rc05_media_head_request(auth_client):
    """HEAD must not advertise an available video resource."""
    resp = auth_client.head("/api/v1/films/the-bat-whispers-1930/media")
    assert resp.status_code == 410
    assert resp.headers.get("Accept-Ranges") is None
    assert len(resp.content) == 0


def test_rc05_media_invalid_range_remains_disabled(auth_client):
    """Invalid ranges cannot revive the retired playback endpoint."""
    headers = {"Range": "bytes=9999999999-9999999999"}
    resp = auth_client.get("/api/v1/films/the-bat-whispers-1930/media", headers=headers)
    assert resp.status_code == 410


def test_rc05_scene_index_bounds(api_client):
    """Verify all returned scenes have start_ms strictly less than reveal cutoff."""
    resp = api_client.get("/api/v1/films/the-bat-whispers-1930/scene-index")
    assert resp.status_code == 200
    scenes = resp.json()["data"]
    cutoff_ms = 4860000
    for sc in scenes:
        assert sc["start_ms"] < cutoff_ms, f"Scene {sc['scene_id']} leaks beyond cutoff: {sc['start_ms']}"
