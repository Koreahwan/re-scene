"""
Static Artifact Spoiler Scanner (R2-10)
Verifies that no static web artifacts, JS bundles, HTML, CSS, or fallback metadata contain unprotected spoilers.
Zero Paid Model Calls.
"""
import os
import re
from pathlib import Path
import pytest

FORBIDDEN_SPOILER_PATTERNS = [
    r"anderson\s+unmasked\s+as\s+['\"]?the\s+bat['\"]?",
    r"anderson\s+is\s+the\s+bat",
    r"detective\s+anderson\s+is\s+secretly\s+the\s+bat",
    r"secret\s+room\s+concealed\s+behind\s+grand\s+fireplace"
]

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "apps" / "web"


def test_static_web_assets_free_of_unprotected_spoilers():
    """Scans all web client files to ensure no hardcoded unmasked spoilers exist in public client files."""
    assert WEB_DIR.exists()

    found_violations = []
    for file_path in WEB_DIR.glob("**/*"):
        if file_path.is_file() and file_path.suffix in [".js", ".html", ".json", ".css", ".ts", ".tsx"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            for pattern in FORBIDDEN_SPOILER_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    found_violations.append(f"{file_path.name}: matched '{pattern}' -> {matches}")

    assert len(found_violations) == 0, f"Found unprotected spoilers in static web assets:\n" + "\n".join(found_violations)
