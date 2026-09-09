"""
Product-Wide i18n Scanner Tool & Audit Script.
Scans apps/web/src for:
1. Korean UI text literals outside of i18n dictionary files and allowlisted metadata.
2. Key parity between en-US.ts and ko-KR.ts.
3. Allowlisted items (native language endonym '한국어', film title '배트 위스퍼스', project provenance).
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Set, Tuple

KOREAN_REGEX = re.compile(r"[\uac00-\ud7a3]")

# Explicit allowlist of permissible Korean literals (canonical data, film titles, proper names)
ALLOWLIST_TERMS = {
    "배트 위스퍼스",  # Korean title of The Bat Whispers (1930)
    "한국어",        # Native endonym in language switcher
    "해커톤",        # Project provenance metadata
}

EXCLUDED_FILES = {
    "ko-KR.ts",      # Korean dictionary
    "en-US.ts",      # English dictionary
    "trustMapper.ts", # Bilingual trust mapper helper
    "formatters.ts"   # Bilingual duration formatter
}

EXCLUDED_DIRS = {
    "testing",       # Test fixture transliterations
    "tests",
    "e2e"
}


def extract_string_literals(source_code: str) -> List[Tuple[int, str]]:
    """Extracts string literals and JSX text with line numbers."""
    lines = source_code.split("\n")
    results = []
    for line_idx, line in enumerate(lines, start=1):
        # Skip single-line comments
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        # Check if line contains Korean characters
        if KOREAN_REGEX.search(line):
            # Check if all Korean matches are in allowlist
            is_allowlisted = any(term in line for term in ALLOWLIST_TERMS)
            if not is_allowlisted:
                results.append((line_idx, stripped))
    return results


def check_i18n_parity(root_dir: Path) -> Tuple[Set[str], Set[str]]:
    en_file = root_dir / "apps" / "web" / "src" / "i18n" / "messages" / "en-US.ts"
    ko_file = root_dir / "apps" / "web" / "src" / "i18n" / "messages" / "ko-KR.ts"

    def get_keys(file_path: Path) -> Set[str]:
        content = file_path.read_text(encoding="utf-8")
        keys = set(re.findall(r"'([a-zA-Z0-9_.]+)':", content))
        return keys

    en_keys = get_keys(en_file)
    ko_keys = get_keys(ko_file)

    missing_in_ko = en_keys - ko_keys
    missing_in_en = ko_keys - en_keys
    return missing_in_ko, missing_in_en


def scan_web_src(root_dir: Path) -> Dict[str, List[Tuple[int, str]]]:
    src_dir = root_dir / "apps" / "web" / "src"
    violations: Dict[str, List[Tuple[int, str]]] = {}

    for path in src_dir.rglob("*.tsx"):
        if path.name in EXCLUDED_FILES or any(d in path.parts for d in EXCLUDED_DIRS):
            continue
        code = path.read_text(encoding="utf-8")
        hits = extract_string_literals(code)
        if hits:
            rel_path = str(path.relative_to(root_dir)).replace("\\", "/")
            violations[rel_path] = hits

    for path in src_dir.rglob("*.ts"):
        if path.name in EXCLUDED_FILES or any(d in path.parts for d in EXCLUDED_DIRS):
            continue
        code = path.read_text(encoding="utf-8")
        hits = extract_string_literals(code)
        if hits:
            rel_path = str(path.relative_to(root_dir)).replace("\\", "/")
            violations[rel_path] = hits

    return violations


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    print("Checking i18n dictionary parity...")
    missing_ko, missing_en = check_i18n_parity(root)
    print(f"Missing in ko-KR: {len(missing_ko)} keys")
    print(f"Missing in en-US: {len(missing_en)} keys")

    print("\nScanning for hardcoded Korean UI text in apps/web/src...")
    violations = scan_web_src(root)
    for file, hits in violations.items():
        print(f"\n{file}:")
        for line_num, text in hits[:5]:
            print(f"  Line {line_num}: {text[:80]}")
    print(f"\nTotal violating files: {len(violations)}")
