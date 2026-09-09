from pathlib import Path
import json
import re

def test_visual_layout_files_exist():
    root = Path(__file__).resolve().parent.parent.parent
    web_dir = root / "apps" / "web" / "src"

    pages = [
        "HomePage.tsx",
        "FilmHubPage.tsx",
        "MagazinePage.tsx",
        "MagazineDetailPage.tsx",
        "CommunityPage.tsx",
        "PostDetailPage.tsx",
        "ProfilePage.tsx",
        "RewatchPage.tsx",
        "ProofDetailPage.tsx",
        "TheoryLabPage.tsx",
        "LoginPage.tsx",
        "SignupPage.tsx",
        "ForgotPasswordPage.tsx"
    ]

    for p in pages:
        page_file = web_dir / "pages" / p
        assert page_file.exists(), f"Page {p} does not exist"

    # Verify i18n files
    i18n_dir = web_dir / "i18n"
    assert (i18n_dir / "LocaleProvider.tsx").exists()
    assert (i18n_dir / "localeTypes.ts").exists()
    assert (i18n_dir / "messages" / "en-US.ts").exists()
    assert (i18n_dir / "messages" / "ko-KR.ts").exists()
    assert (web_dir / "components" / "LanguageSelector.tsx").exists()
    assert (web_dir / "components" / "AuthModal.tsx").exists()

def test_svg_icons_used_and_no_raw_emojis_in_cards():
    root = Path(__file__).resolve().parent.parent.parent
    components_dir = root / "apps" / "web" / "src" / "components"

    movie_card = (components_dir / "MovieCard.tsx").read_text(encoding="utf-8")
    assert "StarIcon" in movie_card
    assert "BookmarkIcon" in movie_card
    assert "ReframeIcon" in movie_card
    assert "★" not in movie_card

    magazine_card = (components_dir / "MagazineCard.tsx").read_text(encoding="utf-8")
    assert "ShieldCheckIcon" in magazine_card
    assert "ShieldAlertIcon" in magazine_card
    assert "ClockIcon" in magazine_card
    assert "🛡️" not in magazine_card
    assert "⏱️" not in magazine_card

    reframe_card = (components_dir / "ReframeCard.tsx").read_text(encoding="utf-8")
    assert "mapTrustNamespace" in reframe_card
    assert "SparklesIcon" in reframe_card

def test_trust_mapper_strict_d4_boundary():
    root = Path(__file__).resolve().parent.parent.parent
    trust_mapper_file = root / "apps" / "web" / "src" / "utils" / "trustMapper.ts"
    content = trust_mapper_file.read_text(encoding="utf-8")

    assert "trustNamespace === 'CANONICAL_VERIFIED'" in content
    assert "verificationStatus === 'VERIFIED_CANON'" in content
    assert "VERIFIED CANON" in content
    assert "ABSTAINED" in content
    assert "ENGINE_INFERENCE" in content
