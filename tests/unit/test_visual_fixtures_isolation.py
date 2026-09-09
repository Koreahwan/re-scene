from pathlib import Path
import re

def test_no_hardcoded_fabricated_data_in_production_pages():
    root = Path(__file__).resolve().parent.parent.parent
    pages_dir = root / "apps" / "web" / "src" / "pages"
    components_dir = root / "apps" / "web" / "src" / "components"

    forbidden_patterns = [
        re.compile(r'moment-01'),
        re.compile(r'sc-004-arrival'),
        re.compile(r'sc-007-flashlight'),
        re.compile(r'fabricated Anderson behavior', re.IGNORECASE),
        re.compile(r'localUnlocked'),
    ]

    for p in list(pages_dir.glob("*.tsx")) + list(components_dir.glob("*.tsx")):
        content = p.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            matches = pat.findall(content)
            assert not matches, f"Found forbidden hardcoded pattern {pat.pattern} in {p.name}"

def test_visual_fixtures_isolation():
    root = Path(__file__).resolve().parent.parent.parent
    use_fixture_file = root / "apps" / "web" / "src" / "testing" / "useVisualFixture.ts"
    assert use_fixture_file.exists()

    content = use_fixture_file.read_text(encoding="utf-8")
    assert "VITE_VISUAL_FIXTURE_MODE" in content
