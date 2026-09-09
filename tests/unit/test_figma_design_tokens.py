import json
import re
from pathlib import Path

def test_figma_design_tokens_synchronization():
    root = Path(__file__).resolve().parent.parent.parent
    token_json_path = root / "docs" / "design" / "figma" / "DESIGN_TOKEN_MAP.json"
    tokens_css_path = root / "apps" / "web" / "src" / "styles" / "tokens.css"

    assert token_json_path.exists(), f"Missing {token_json_path}"
    assert tokens_css_path.exists(), f"Missing {tokens_css_path}"

    with open(token_json_path, "r", encoding="utf-8") as f:
        token_map = json.load(f)

    with open(tokens_css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    # Verify background colors
    assert f"--bg-app: {token_map['colors']['background']['default']};" in css_content
    assert f"--bg-surface: {token_map['colors']['background']['paper']};" in css_content
    assert f"--bg-surface-raised: {token_map['colors']['background']['surface']};" in css_content

    # Verify primary colors
    for step, hex_val in token_map["colors"]["primary"].items():
        assert f"--primary-{step}: {hex_val};" in css_content

    # Verify accent colors
    for accent_name, hex_val in token_map["colors"]["accent"].items():
        assert f"--accent-{accent_name}: {hex_val};" in css_content

    # Verify font families
    assert "--font-primary: 'Pretendard'" in css_content
    assert "--font-display: '42dot Sans'" in css_content
    assert "--font-code: 'IBM Plex Sans KR'" in css_content

    # Verify radii
    for r_name, r_val in token_map["radii"].items():
        assert f"--radius-{r_name}: {r_val};" in css_content
