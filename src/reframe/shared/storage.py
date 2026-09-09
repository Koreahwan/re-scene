"""
Reframe V7 Storage Abstraction (GCS + Local Development Adapter)
"""
import os
import hashlib
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import structlog
from src.reframe.shared.config import settings

logger = structlog.get_logger(__name__)

_WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    prefix + number for prefix in ("COM", "LPT") for number in "123456789¹²³"
}


class StorageBackend(ABC):
    @abstractmethod
    async def put_object(self, path: str, data: bytes, content_type: str = "application/json") -> Tuple[str, str]:
        """Returns (uri, sha256_hex)"""
        pass

    @abstractmethod
    async def get_object(self, path: str) -> Optional[bytes]:
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str):
        self.base_dir = str(Path(base_dir).resolve())
        os.makedirs(self.base_dir, exist_ok=True)

    def _object_path(self, path: str) -> str:
        # Object keys use relative POSIX components on every host. Never accept
        # Windows drive/UNC/ADS syntax, even when the service runs on Linux.
        if (not path or path.startswith("/") or "\\" in path or ":" in path
                or any(ord(char) < 32 for char in path)
                or any(part in ("", ".", "..") or part.rstrip(" .") != part
                       or part.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_RESERVED_NAMES
                       for part in path.split("/"))):
            raise ValueError("Invalid storage object key")
        base = Path(self.base_dir)
        resolved = (base / path).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError("Storage object key escapes its root")
        return str(resolved)

    async def put_object(self, path: str, data: bytes, content_type: str = "application/json") -> Tuple[str, str]:
        full_path = self._object_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(data)
        sha256 = hashlib.sha256(data).hexdigest()
        uri = f"file://{full_path.replace(os.sep, '/')}"
        return uri, sha256

    async def get_object(self, path: str) -> Optional[bytes]:
        full_path = self._object_path(path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, "rb") as f:
            return f.read()

    async def exists(self, path: str) -> bool:
        full_path = self._object_path(path)
        return os.path.exists(full_path)


class GCSStorageBackend(StorageBackend):
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        # Note: Production GCS implementation uses google-cloud-storage if configured

    async def put_object(self, path: str, data: bytes, content_type: str = "application/json") -> Tuple[str, str]:
        sha256 = hashlib.sha256(data).hexdigest()
        uri = f"gs://{self.bucket_name}/{path.lstrip('/')}"
        logger.info("GCS put_object stub/prod", uri=uri, bytes=len(data))
        return uri, sha256

    async def get_object(self, path: str) -> Optional[bytes]:
        logger.info("GCS get_object stub/prod", path=path)
        return None

    async def exists(self, path: str) -> bool:
        return False


def get_storage() -> StorageBackend:
    if settings.STORAGE_BACKEND == "gcs" and settings.GCS_BUCKET_NAME:
        return GCSStorageBackend(settings.GCS_BUCKET_NAME)
    return LocalStorageBackend(settings.LOCAL_STORAGE_DIR)
