"""Local-only upload and storage boundary regressions; no production data."""
import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from apps.api.routers.account import sanitized_photo
from src.reframe.shared.storage import LocalStorageBackend


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [
    "../outside", "nested/../../outside", "/outside", r"..\outside",
    r"C:\outside", "C:outside", r"\\server\share\outside", "file:stream",
    "", ".", "nested/../inside", "bad\x00name", "CON", "NUL.txt", "COM1", "file.", "file ",
])
async def test_storage_rejects_unsafe_keys(tmp_path, key):
    storage = LocalStorageBackend(str(tmp_path / "objects"))
    for operation in (storage.get_object, storage.exists):
        with pytest.raises(ValueError):
            await operation(key)
    with pytest.raises(ValueError):
        await storage.put_object(key, b"test")
    assert not (tmp_path / "outside").exists()


@pytest.mark.asyncio
async def test_storage_roundtrip(tmp_path):
    storage = LocalStorageBackend(str(tmp_path / "objects"))
    _, digest = await storage.put_object("films/one/result.json", b"{}")
    assert len(digest) == 64
    assert await storage.get_object("films/one/result.json") == b"{}"
    assert await storage.exists("films/one/result.json")
    assert await storage.get_object("missing") is None
    assert not await storage.exists("missing")


@pytest.mark.asyncio
async def test_storage_symlink_escape(tmp_path):
    storage = LocalStorageBackend(str(tmp_path / "objects"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"preserve")
    try:
        (tmp_path / "objects" / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Host does not permit symlinks: {exc}")
    with pytest.raises(ValueError):
        await storage.get_object("link/sentinel")
    with pytest.raises(ValueError):
        await storage.exists("link/sentinel")
    with pytest.raises(ValueError):
        await storage.put_object("link/sentinel", b"replace")
    assert (outside / "sentinel").read_bytes() == b"preserve"


def photo_uri(raw, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def test_photo_reencodes_and_strips_metadata_and_trailing_payload():
    source = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "private metadata sentinel"
    Image.new("RGB", (300, 100), "red").save(source, format="PNG", exif=exif)
    result = sanitized_photo(photo_uri(source.getvalue() + b"<script>sentinel</script>"))
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "PNG"
        assert max(image.size) <= 256
        assert not image.getexif()
    assert b"private metadata sentinel" not in result
    assert b"<script>" not in result


@pytest.mark.parametrize("raw,mime", [
    (b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>', "image/png"),
    (b"not an image", "image/jpeg"),
    (b"MZ" + b"x" * 100, "image/png"),
    (b"x" * 1_000_001, "image/png"),
], ids=["svg", "text", "executable", "over-byte-limit"])
def test_photo_rejects_invalid_or_oversized_data(raw, mime):
    with pytest.raises(HTTPException) as failure:
        sanitized_photo(photo_uri(raw, mime))
    assert failure.value.status_code == 422


def test_photo_rejects_mime_mismatch():
    source = io.BytesIO()
    Image.new("RGB", (10, 10)).save(source, format="PNG")
    with pytest.raises(HTTPException):
        sanitized_photo(photo_uri(source.getvalue(), "image/jpeg"))


def test_photo_rejects_excessive_dimensions():
    source = io.BytesIO()
    Image.new("RGB", (2001, 2000)).save(source, format="PNG")
    with pytest.raises(HTTPException) as failure:
        sanitized_photo(photo_uri(source.getvalue()))
    assert failure.value.status_code == 422


@pytest.mark.asyncio
async def test_profile_upload_requires_auth_and_csrf_and_serves_png():
    import uuid
    from httpx import ASGITransport, AsyncClient
    from apps.api.main import app

    source = io.BytesIO()
    Image.new("RGB", (12, 12), "blue").save(source, format="PNG")
    payload = {"display_name": "Upload boundary test", "photo_data": photo_uri(source.getvalue())}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.patch("/api/v1/profiles/me", json=payload)
        assert denied.status_code == 401
        login = await client.post("/api/v1/auth/dev-login", json={
            "email": f"upload-{uuid.uuid4().hex}@example.com", "display_name": "Upload test"})
        assert login.status_code == 200
        denied = await client.patch("/api/v1/profiles/me", json=payload)
        assert denied.status_code == 403
        headers = {"X-CSRF-Token": login.json()["data"]["csrf_token"]}
        saved = await client.patch("/api/v1/profiles/me", json=payload, headers=headers)
        assert saved.status_code == 200
        avatar = await client.get(saved.json()["data"]["avatar_url"])
        assert avatar.status_code == 200
        assert avatar.headers["content-type"] == "image/png"
        assert avatar.headers["x-content-type-options"] == "nosniff"
        assert b"PNG" in avatar.content[:8]
        rejected = await client.patch("/api/v1/profiles/me", json={**payload,
            "photo_data": photo_uri(b"<script>test</script>")}, headers=headers)
        assert rejected.status_code == 422
        unchanged = await client.get(saved.json()["data"]["avatar_url"])
        assert unchanged.content == avatar.content
