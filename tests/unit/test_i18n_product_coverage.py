"""
Test for Product-Wide i18n Dictionary Parity and Zero Hardcoded String Violations.
Ensures en-US and ko-KR have 100% key parity and apps/web/src has 0 unlocalized UI strings.
"""
from pathlib import Path
from tools.scan_i18n import check_i18n_parity, scan_web_src


def test_i18n_dictionary_key_parity():
    root_dir = Path(__file__).resolve().parent.parent.parent
    missing_ko, missing_en = check_i18n_parity(root_dir)

    assert len(missing_ko) == 0, f"Keys missing in ko-KR: {sorted(list(missing_ko))}"
    assert len(missing_en) == 0, f"Keys missing in en-US: {sorted(list(missing_en))}"


def test_i18n_zero_hardcoded_korean_violations():
    root_dir = Path(__file__).resolve().parent.parent.parent
    violations = scan_web_src(root_dir)

    assert len(violations) == 0, f"Hardcoded UI string violations detected in {len(violations)} files: {list(violations.keys())}"
