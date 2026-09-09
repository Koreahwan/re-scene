import json
import hashlib
from pathlib import Path
from typing import Dict, Any


def verify_asset_manifest(manifest_path: Path) -> Dict[str, Any]:
    """
    Validates asset rights manifest and metadata before permitting any ingestion.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Asset manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if manifest.get("asset_status") != "APPROVED":
        raise ValueError(f"Asset status is '{manifest.get('asset_status')}', must be 'APPROVED'")

    rights = manifest.get("rights", {})
    if rights.get("review_status") != "APPROVED":
        raise ValueError(f"Rights review status is '{rights.get('review_status')}', must be 'APPROVED'")

    video_meta = manifest.get("canonical_video") or manifest.get("video", {})
    if not video_meta.get("sha256") or not video_meta.get("source_url"):
        raise ValueError("Video metadata missing required sha256 or source_url")

    return {
        "status": "APPROVED",
        "movie_id": manifest.get("movie_id"),
        "title": manifest.get("title"),
        "video_sha256": video_meta.get("sha256"),
        "territories": rights.get("territories_reviewed", []),
        "active_dataset_version": manifest.get("active_dataset_version"),
    }


if __name__ == "__main__":
    p = Path(__file__).resolve().parent.parent.parent / "data" / "manifests" / "asset_manifest.json"
    result = verify_asset_manifest(p)
    print(f"Asset verification passed: {result}")
