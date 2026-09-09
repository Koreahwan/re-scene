import shutil
import subprocess
import pytest


def test_gitleaks_zero_leaks_in_repository():
    """
    Executes official Gitleaks binary across the entire repository to ensure
    zero API keys, private keys, service account credentials, or tokens are committed.
    """
    gitleaks_bin = shutil.which("gitleaks")
    if gitleaks_bin is None:
        pytest.skip("Install Gitleaks to run the repository secret scan")

    result = subprocess.run(
        [gitleaks_bin, "git", ".", "--redact=100", "--no-banner"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    print("\n=== GITLEAKS AUDIT OUTPUT ===")
    if result.stdout:
        print(result.stdout.encode("ascii", "replace").decode("ascii"))
    if result.stderr:
        print(result.stderr.encode("ascii", "replace").decode("ascii"))
    print("=============================")

    assert result.returncode == 0, f"Gitleaks detected security leaks!\n{result.stdout}\n{result.stderr}"
