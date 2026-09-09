from pathlib import Path
import re

def test_spoiler_gate_has_no_client_local_unlocked_bypass():
    root = Path(__file__).resolve().parent.parent.parent
    spoiler_gate_file = root / "apps" / "web" / "src" / "components" / "SpoilerGate.tsx"
    assert spoiler_gate_file.exists()

    content = spoiler_gate_file.read_text(encoding="utf-8")
    assert "localUnlocked" not in content, "Client-local bypass state found in SpoilerGate.tsx"
    assert "setLocalUnlocked" not in content, "Client-local unlock setter found in SpoilerGate.tsx"
    assert "isSpoilerUnlocked" not in content, "Client-local isSpoilerUnlocked found in SpoilerGate.tsx"

    # Must check strictly visibility === 'VISIBLE'
    assert "visibility === 'VISIBLE'" in content
