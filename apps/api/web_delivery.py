"""
Reframe V7 Web Delivery Module
Secure, isolated static asset delivery with gzip negotiation, path traversal prevention,
content-hashed immutable caching, and SPA HTML navigation handling.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import mimetypes
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse

from fastapi import FastAPI, HTTPException, Request, Response, status

# Ensure mimetypes knows common web extensions
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/html", ".html")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/x-icon", ".ico")

COMPRESSIBLE_EXTENSIONS: Set[str] = {
    ".js", ".mjs", ".css", ".svg", ".json", ".html", ".xml", ".txt", ".webmanifest"
}

NON_COMPRESSIBLE_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico",
    ".mp4", ".webm", ".mp3", ".wav", ".gz", ".zip", ".woff", ".woff2"
}

STATIC_FILE_EXTENSIONS: Set[str] = {
    ".js", ".mjs", ".cjs", ".css", ".map", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav",
    ".pdf", ".txt", ".xml", ".webmanifest",
    ".ts", ".tsx", ".py", ".sh", ".ps1", ".env", ".yaml", ".yml",
}

FORBIDDEN_NAMES: Set[str] = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "tsconfig.json", "tsconfig.node.json", "docker-compose.yml",
    "docker-compose.yaml", "dockerfile", ".env"
}

FORBIDDEN_EXTENSIONS: Set[str] = {
    ".ts", ".tsx", ".py", ".pyc", ".sh", ".ps1", ".bat", ".cmd",
    ".map", ".env", ".yaml", ".yml", ".toml", ".ini", ".conf",
    ".sql", ".db", ".sqlite"
}

FORBIDDEN_SEGMENTS: Set[str] = {
    "src", "node_modules", "tests", "e2e", "docs", ".git",
    ".agents", "infra", "tools", "db", "artifacts"
}

# Supported SPA UI route top-level segments from App.tsx
SPA_UI_TOP_SEGMENTS: Set[str] = {
    "films", "audience-lab", "magazine", "proofs", "moments",
    "rewatch", "theory-lab", "posts", "community", "profile",
    "me", "login", "signup", "forgot-password", "reset-password", "notice", "box-office"
}

FINGERPRINT_PATTERN = re.compile(r"-[a-zA-Z0-9_-]{8,}\.(?:js|mjs|css)$")


def parse_accept_header(accept_header: Optional[str]) -> List[Tuple[str, float]]:
    """Parse HTTP Accept header into a list of (media_type, q_value) tuples."""
    if not accept_header:
        return []
    entries: List[Tuple[str, float]] = []
    for part in accept_header.split(","):
        part = part.strip()
        if not part:
            continue
        subparts = [sp.strip() for sp in part.split(";")]
        mime_type = subparts[0].lower()
        q = 1.0
        for param in subparts[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:].strip())
                except (ValueError, TypeError):
                    q = 0.0
        entries.append((mime_type, q))
    return entries


def is_html_requested(request: Request) -> bool:
    """
    Check if the client specifically accepts HTML (browser document request).
    - Returns True if text/html or application/xhtml+xml is present with q > 0.
    - Returns False if Accept is application/json or */* (legacy API requests).
    - Returns False if text/html has q=0.
    """
    accept_val = request.headers.get("accept")
    if not accept_val:
        return False
    parsed = parse_accept_header(accept_val)
    for mime_type, q in parsed:
        if mime_type in ("text/html", "application/xhtml+xml"):
            if q > 0.0:
                return True
    return False


def is_gzip_accepted(request: Request) -> bool:
    """Check if client accepts gzip encoding with q > 0."""
    ae = request.headers.get("accept-encoding")
    if not ae:
        return False
    gzip_q = None
    star_q = None
    for part in ae.split(","):
        part = part.strip()
        if not part:
            continue
        subparts = [sp.strip() for sp in part.split(";")]
        enc = subparts[0].lower()
        q = 1.0
        for param in subparts[1:]:
            if param.lower().startswith("q="):
                try:
                    q = float(param[2:].strip())
                except (ValueError, TypeError):
                    q = 0.0
        if enc == "gzip":
            gzip_q = q
        elif enc == "*":
            star_q = q
    if gzip_q is not None:
        return gzip_q > 0.0
    if star_q is not None:
        return star_q > 0.0
    return False


def is_fingerprinted_asset(filename: str) -> bool:
    """Check if a JS/CSS file contains a build fingerprint hash."""
    return bool(FINGERPRINT_PATTERN.search(filename))


def is_compressible_type(content_type: str, filename: str) -> bool:
    """Determine if a file should be gzip-compressed."""
    ext = Path(filename).suffix.lower()
    if ext in NON_COMPRESSIBLE_EXTENSIONS:
        return False
    if ext in COMPRESSIBLE_EXTENSIONS:
        return True
    ct = content_type.lower()
    if ct.startswith("text/"):
        return True
    if any(s in ct for s in ("javascript", "json", "xml", "svg")):
        return True
    return False


def compute_opaque_hash(content: bytes) -> str:
    """Generate SHA-256 derived hex string."""
    return hashlib.sha256(content).hexdigest()[:16]


def is_safe_relative_path(path_str: str) -> bool:
    """
    Validate that path is safe against traversal, dotfiles, and forbidden files.
    """
    if not path_str:
        return True
    # Reject backslashes or encoded backslashes
    if "\\" in path_str or "%5c" in path_str.lower():
        return False
    unquoted = urllib.parse.unquote(path_str)
    if "\\" in unquoted or "\0" in unquoted:
        return False

    # Split into components
    parts = [p for p in unquoted.replace("\\", "/").split("/") if p]
    for part in parts:
        if part in (".", "..") or part.startswith("."):
            return False
        part_lower = part.lower()
        if part_lower in FORBIDDEN_NAMES or any(part_lower.startswith(f) for f in ("tsconfig", "vite.config", ".env")):
            return False
        if part_lower in FORBIDDEN_SEGMENTS:
            return False
        # Check suffix
        ext = Path(part).suffix.lower()
        if ext in FORBIDDEN_EXTENSIONS:
            return False
    return True


def is_spa_ui_route(path_str: str) -> bool:
    """Determine if route matches a known React SPA UI view."""
    clean = path_str.strip("/")
    if not clean or clean == "index.html":
        return True
    top = clean.split("/")[0]
    return top in SPA_UI_TOP_SEGMENTS


def is_contained_in_roots(resolved_file: Path, roots: List[Path]) -> bool:
    """Verify that a resolved file is strictly contained within at least one authorized root."""
    for root in roots:
        try:
            resolved_file.relative_to(root.resolve())
            return True
        except (ValueError, RuntimeError):
            continue
    return False


def weak_etag_matches(client_tag: str, server_opaque: str) -> bool:
    """RFC 9110 weak ETag comparison."""
    c = client_tag.strip()
    if c == "*":
        return True
    c_clean = c.lstrip("W/").strip('"')
    s_clean = server_opaque.strip().lstrip("W/").strip('"')
    return c_clean == s_clean


MAX_CACHE_ENTRIES: int = 64
MAX_CACHE_RETAINED_BYTES: int = 32 * 1024 * 1024  # 32 MiB total memory budget
MAX_CACHE_SINGLE_FILE_BYTES: int = 8 * 1024 * 1024  # 8 MiB max per cached item


class StaticFileCacheEntry:
    """In-memory cache entry holding raw content, SHA hash, and optional gzip bytes."""
    __slots__ = ("path", "mtime_ns", "size", "raw_content", "raw_hash", "gzip_content", "retained_bytes")

    def __init__(
        self,
        path: Path,
        mtime_ns: int,
        size: int,
        raw_content: bytes,
        raw_hash: str,
        gzip_content: Optional[bytes] = None,
    ):
        self.path = path
        self.mtime_ns = mtime_ns
        self.size = size
        self.raw_content = raw_content
        self.raw_hash = raw_hash
        self.gzip_content = gzip_content
        self.retained_bytes = len(raw_content) + (len(gzip_content) if gzip_content else 0)


class BoundedStaticFileCache:
    """
    Thread-safe, LRU-evicting in-memory cache for public static file processing data.
    - Bounded entries (max_entries <= 64)
    - Bounded memory footprint (retained_bytes <= 32 MiB)
    - Single-file cache bypass for oversized files (> 8 MiB)
    - Instant invalidation when file mtime_ns or size changes on disk
    - Fail-closed: does not cache errors or missing files
    """
    def __init__(
        self,
        max_entries: int = MAX_CACHE_ENTRIES,
        max_retained_bytes: int = MAX_CACHE_RETAINED_BYTES,
        max_single_file_bytes: int = MAX_CACHE_SINGLE_FILE_BYTES,
    ):
        self.max_entries = max_entries
        self.max_retained_bytes = max_retained_bytes
        self.max_single_file_bytes = max_single_file_bytes
        self._lock = threading.Lock()
        self._entries: collections.OrderedDict[Path, StaticFileCacheEntry] = collections.OrderedDict()
        self._current_retained_bytes = 0

    def get(self, path: Path) -> Optional[StaticFileCacheEntry]:
        """Retrieve entry if valid and stat has not changed on disk."""
        with self._lock:
            entry = self._entries.get(path)
            if entry is None:
                return None

            try:
                st = path.stat()
            except OSError:
                self._evict_path_locked(path)
                return None

            if st.st_mtime_ns != entry.mtime_ns or st.st_size != entry.size:
                self._evict_path_locked(path)
                return None

            self._entries.move_to_end(path)
            return entry

    def put(
        self,
        path: Path,
        mtime_ns: int,
        size: int,
        raw_content: bytes,
        raw_hash: str,
        gzip_content: Optional[bytes] = None,
    ) -> Optional[StaticFileCacheEntry]:
        """Store entry subject to single-file limit and global LRU budget."""
        needed = len(raw_content) + (len(gzip_content) if gzip_content else 0)
        if needed > self.max_single_file_bytes or needed > self.max_retained_bytes:
            return None

        entry = StaticFileCacheEntry(
            path=path,
            mtime_ns=mtime_ns,
            size=size,
            raw_content=raw_content,
            raw_hash=raw_hash,
            gzip_content=gzip_content,
        )

        with self._lock:
            if path in self._entries:
                old_entry = self._entries.pop(path)
                self._current_retained_bytes -= old_entry.retained_bytes

            while self._entries and (
                len(self._entries) >= self.max_entries
                or self._current_retained_bytes + needed > self.max_retained_bytes
            ):
                _, popped = self._entries.popitem(last=False)
                self._current_retained_bytes -= popped.retained_bytes

            if len(self._entries) < self.max_entries and self._current_retained_bytes + needed <= self.max_retained_bytes:
                self._entries[path] = entry
                self._current_retained_bytes += needed
                return entry

            return None

    def update_gzip(
        self,
        path: Path,
        gzip_content: bytes,
        expected_entry: Optional[StaticFileCacheEntry] = None,
        expected_raw_hash: Optional[str] = None,
    ) -> Optional[StaticFileCacheEntry]:
        """Attach precomputed gzip bytes to an existing cached entry if memory allows and entry is unchanged."""
        with self._lock:
            entry = self._entries.get(path)
            if entry is None or entry.gzip_content is not None:
                return entry

            # Discard stale gzip updates if the cached entry was replaced or modified
            if expected_entry is not None and entry is not expected_entry:
                return None
            if expected_raw_hash is not None and entry.raw_hash != expected_raw_hash:
                return None

            add_bytes = len(gzip_content)
            combined_bytes = len(entry.raw_content) + add_bytes
            # Both combined per-entry cap and global budget must be satisfied
            if combined_bytes > self.max_single_file_bytes or combined_bytes > self.max_retained_bytes:
                return entry

            while self._entries and (self._current_retained_bytes + add_bytes > self.max_retained_bytes):
                candidate_key = next((k for k in self._entries if k != path), None)
                if candidate_key is None:
                    break
                popped = self._entries.pop(candidate_key)
                self._current_retained_bytes -= popped.retained_bytes

            if self._current_retained_bytes + add_bytes <= self.max_retained_bytes:
                entry.gzip_content = gzip_content
                entry.retained_bytes += add_bytes
                self._current_retained_bytes += add_bytes
                self._entries.move_to_end(path)

            return entry

    def _evict_path_locked(self, path: Path) -> None:
        if path in self._entries:
            popped = self._entries.pop(path)
            self._current_retained_bytes -= popped.retained_bytes

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._current_retained_bytes = 0

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "retained_bytes": self._current_retained_bytes,
                "max_entries": self.max_entries,
                "max_retained_bytes": self.max_retained_bytes,
            }


class WebDeliveryHandler:
    def __init__(
        self,
        dist_dir: Path,
        web_dir: Optional[Path] = None,
        public_dir: Optional[Path] = None,
    ):
        self.dist_dir = dist_dir.resolve()
        self.web_dir = web_dir.resolve() if web_dir else None
        self.public_dir = (
            public_dir.resolve()
            if public_dir
            else (self.web_dir / "public").resolve()
            if self.web_dir and (self.web_dir / "public").exists()
            else None
        )
        # Original allowed static roots (never promoted from symlinks)
        self.allowed_static_roots: List[Path] = [self.dist_dir]
        if self.public_dir:
            self.allowed_static_roots.append(self.public_dir)

        # In-memory bounded cache for public static file content, hashes, and compressed representations
        self.file_cache: BoundedStaticFileCache = BoundedStaticFileCache()

    def _resolve_file(self, rel_path: str) -> Optional[Path]:
        """Safely resolve relative path to an existing file strictly within dist/public roots."""
        if not is_safe_relative_path(rel_path):
            return None

        clean_path = Path(urllib.parse.unquote(rel_path))
        if clean_path.is_absolute():
            return None

        candidates = [
            self.dist_dir / clean_path,
        ]
        if self.public_dir:
            candidates.append(self.public_dir / clean_path)

        for cand in candidates:
            try:
                resolved = cand.resolve()
                if resolved.is_file():
                    if is_contained_in_roots(resolved, self.allowed_static_roots):
                        if (
                            resolved.name.lower() in FORBIDDEN_NAMES
                            or resolved.suffix.lower() in FORBIDDEN_EXTENSIONS
                        ):
                            return None
                        return resolved
            except Exception:
                continue

        return None

    def build_file_response(
        self,
        file_path: Path,
        request: Request,
        is_html: bool = False,
        content_override: Optional[bytes] = None,
    ) -> Response:
        """Construct a secure, cached, compressed HTTP Response for a static file."""
        filename = file_path.name
        is_html_file = (
            is_html
            or filename == "index.html"
            or file_path.suffix.lower() in (".html", ".htm")
        )

        content_type, _ = mimetypes.guess_type(str(file_path))
        if is_html_file:
            content_type = "text/html; charset=utf-8"
        elif not content_type:
            content_type = "application/octet-stream"

        compressible = is_compressible_type(content_type, filename)
        client_wants_gzip = is_gzip_accepted(request)

        cached_entry: Optional[StaticFileCacheEntry] = None
        if content_override is not None:
            raw_content = content_override
            raw_hash = compute_opaque_hash(raw_content)
            gzip_content = None
        else:
            cached_entry = self.file_cache.get(file_path)
            if cached_entry is not None:
                raw_content = cached_entry.raw_content
                raw_hash = cached_entry.raw_hash
                gzip_content = cached_entry.gzip_content
            else:
                try:
                    st = file_path.stat()
                    raw_content = file_path.read_bytes()
                except Exception:
                    raise HTTPException(status_code=404, detail="File not found")

                raw_hash = compute_opaque_hash(raw_content)
                gzip_content = None
                if compressible and client_wants_gzip:
                    gzip_content = gzip.compress(raw_content, compresslevel=6)

                cached_entry = self.file_cache.put(
                    path=file_path,
                    mtime_ns=st.st_mtime_ns,
                    size=st.st_size,
                    raw_content=raw_content,
                    raw_hash=raw_hash,
                    gzip_content=gzip_content,
                )

        if compressible and client_wants_gzip and gzip_content is None:
            gzip_content = gzip.compress(raw_content, compresslevel=6)
            if cached_entry is not None:
                self.file_cache.update_gzip(
                    file_path,
                    gzip_content,
                    expected_entry=cached_entry,
                    expected_raw_hash=raw_hash,
                )

        # Cache-Control policy:
        # - HTML is ALWAYS no-cache (never immutable, never 3600)
        # - Fingerprinted JS/CSS is immutable
        # - Fixed assets are revalidatable (3600 must-revalidate)
        if is_html_file:
            cache_control = "no-cache"
        elif is_fingerprinted_asset(filename):
            cache_control = "public, max-age=31536000, immutable"
        else:
            cache_control = "public, max-age=3600, must-revalidate"

        # ETag 304 validation (RFC 9110 weak comparison)
        if_none_match = request.headers.get("if-none-match")
        if if_none_match:
            client_etags = [t.strip() for t in if_none_match.split(",")]
            if any(weak_etag_matches(ce, raw_hash) for ce in client_etags):
                headers = {
                    "ETag": f'W/"{raw_hash}"',
                    "Cache-Control": cache_control,
                    "Vary": "Accept-Encoding",
                }
                return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

        # Range 206 Handling with If-Range verification
        range_header = request.headers.get("range")
        range_valid = True
        if range_header and range_header.startswith("bytes="):
            if_range = request.headers.get("if-range")
            if if_range:
                stripped_if_range = if_range.strip()
                if stripped_if_range.startswith("W/") or stripped_if_range != f'"{raw_hash}"':
                    range_valid = False

            if range_valid:
                try:
                    range_spec = range_header[6:].strip()
                    total_len = len(raw_content)
                    start_str, end_str = range_spec.split("-", 1)
                    start_str, end_str = start_str.strip(), end_str.strip()
                    if start_str and end_str:
                        start = int(start_str)
                        end = min(int(end_str), total_len - 1)
                    elif start_str and not end_str:
                        start = int(start_str)
                        end = total_len - 1
                    elif not start_str and end_str:
                        start = max(0, total_len - int(end_str))
                        end = total_len - 1
                    else:
                        start, end = 0, total_len - 1

                    if 0 <= start <= end < total_len:
                        part = raw_content[start:end + 1]
                        headers = {
                            "Content-Type": content_type,
                            "Content-Range": f"bytes {start}-{end}/{total_len}",
                            "Content-Length": str(len(part)),
                            "Accept-Ranges": "bytes",
                            "ETag": f'"{raw_hash}"',
                            "Cache-Control": cache_control,
                        }
                        body = b"" if request.method == "HEAD" else part
                        return Response(content=body, status_code=status.HTTP_206_PARTIAL_CONTENT, headers=headers)
                except Exception:
                    pass

        # Gzip compression negotiation
        headers = {
            "Content-Type": content_type,
            "Cache-Control": cache_control,
            "Accept-Ranges": "bytes",
        }
        if compressible:
            headers["Vary"] = "Accept-Encoding"

        if compressible and client_wants_gzip:
            compressed = gzip_content if gzip_content is not None else gzip.compress(raw_content, compresslevel=6)
            headers["ETag"] = f'W/"{raw_hash}"'
            headers["Content-Encoding"] = "gzip"
            headers["Content-Length"] = str(len(compressed))
            body = b"" if request.method == "HEAD" else compressed
        else:
            headers["ETag"] = f'"{raw_hash}"'
            headers["Content-Length"] = str(len(raw_content))
            body = b"" if request.method == "HEAD" else raw_content

        return Response(content=body, status_code=status.HTTP_200_OK, headers=headers)

    def serve_index_html(self, request: Request) -> Response:
        """Serve dist/index.html (or fallback raw web index) with no-cache, verified boundaries."""
        dist_index = self.dist_dir / "index.html"
        if dist_index.is_file():
            resolved = dist_index.resolve()
            if is_contained_in_roots(resolved, [self.dist_dir]):
                return self.build_file_response(resolved, request, is_html=True)
            raise HTTPException(status_code=404, detail="Index not found")

        if self.web_dir:
            raw_index = self.web_dir / "index.html"
            if raw_index.is_file():
                resolved = raw_index.resolve()
                if is_contained_in_roots(resolved, [self.web_dir]):
                    return self.build_file_response(resolved, request, is_html=True)
            raise HTTPException(status_code=404, detail="Index not found")

        fallback = b"<h1>Reframe V7 Active</h1><p>API docs at <a href='/docs'>/docs</a></p>"
        headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache",
            "Content-Length": str(len(fallback)),
            "ETag": f'"{compute_opaque_hash(fallback)}"',
            "Vary": "Accept-Encoding",
        }
        return Response(content=b"" if request.method == "HEAD" else fallback, status_code=status.HTTP_200_OK, headers=headers)

    def serve_styles(self, request: Request) -> Response:
        """Serve styles.css with revalidatable cache, verified boundaries."""
        # 1. Check web_dir / styles.css
        if self.web_dir:
            cand = self.web_dir / "styles.css"
            if cand.is_file():
                resolved = cand.resolve()
                if is_contained_in_roots(resolved, [self.web_dir, self.dist_dir]):
                    return self.build_file_response(resolved, request)
                # Escaped web_dir via symlink -> 404
                raise HTTPException(status_code=404, detail="styles.css not found")

        # 2. Check dist_dir / styles.css
        cand_dist = self.dist_dir / "styles.css"
        if cand_dist.is_file():
            resolved = cand_dist.resolve()
            if is_contained_in_roots(resolved, [self.dist_dir]):
                return self.build_file_response(resolved, request)

        raise HTTPException(status_code=404, detail="styles.css not found")

    def serve_asset(self, asset_path: str, request: Request) -> Response:
        """Serve a static asset under /assets/."""
        if not is_safe_relative_path(asset_path):
            raise HTTPException(status_code=404, detail="Asset not found")

        clean_path = Path(urllib.parse.unquote(asset_path))
        # Reject direct html requests under /assets/ as assets
        if clean_path.name == "index.html" or clean_path.suffix.lower() in (".html", ".htm"):
            raise HTTPException(status_code=404, detail="Asset not found")

        resolved = None
        for base in [self.dist_dir / "assets", self.dist_dir]:
            cand = base / clean_path
            try:
                if cand.is_file():
                    cand_res = cand.resolve()
                    if is_contained_in_roots(cand_res, self.allowed_static_roots):
                        if (
                            cand_res.name.lower() in FORBIDDEN_NAMES
                            or cand_res.suffix.lower() in FORBIDDEN_EXTENSIONS
                        ):
                            continue
                        resolved = cand_res
                        break
            except Exception:
                continue

        if not resolved and self.public_dir:
            for base in [self.public_dir / "assets", self.public_dir]:
                cand = base / clean_path
                try:
                    if cand.is_file():
                        cand_res = cand.resolve()
                        if is_contained_in_roots(cand_res, self.allowed_static_roots):
                            if (
                                cand_res.name.lower() in FORBIDDEN_NAMES
                                or cand_res.suffix.lower() in FORBIDDEN_EXTENSIONS
                            ):
                                continue
                            resolved = cand_res
                            break
                except Exception:
                    continue

        if not resolved:
            raise HTTPException(status_code=404, detail="Asset not found")

        return self.build_file_response(resolved, request)

    def handle_spa_or_asset(self, full_path: str, request: Request) -> Response:
        """
        Handle catch-all requests:
        1. Guard reserved prefixes (api, health, docs, etc.) -> 404
        2. Reject path traversals / forbidden names -> 404
        3. If requesting index.html -> serve index.html with no-cache
        4. Check if matching static file exists -> serve it
        5. If asset path or has static extension but file missing -> 404 (NEVER mask asset 404 as HTML!)
        6. If browser requests HTML for known SPA UI route -> serve index.html
        7. Otherwise -> 404
        """
        # 1. Reserved prefixes
        if full_path.startswith((
            "api/", "live", "ready", "health", "docs", "redoc", "openapi.json"
        )):
            raise HTTPException(status_code=404, detail="Not Found")

        # 2. Safety check
        if not is_safe_relative_path(full_path):
            raise HTTPException(status_code=404, detail="Not Found")

        # 3. Explicit index.html route
        if full_path == "index.html":
            return self.serve_index_html(request)

        # 4. Check for existing static file
        resolved_file = self._resolve_file(full_path)
        if resolved_file:
            return self.build_file_response(resolved_file, request)

        # 5. Check if missing asset or file with static extension
        ext = Path(full_path).suffix.lower()
        if full_path.startswith("assets/") or ext in STATIC_FILE_EXTENSIONS:
            raise HTTPException(status_code=404, detail="Asset not found")

        # 6. SPA Route check with HTML Accept header
        if is_html_requested(request) and is_spa_ui_route(full_path):
            resp = self.serve_index_html(request)
            # Merge Vary: Accept
            current_vary = resp.headers.get("vary")
            if current_vary:
                parts = [p.strip() for p in current_vary.split(",")]
                if "Accept" not in parts:
                    parts.append("Accept")
                resp.headers["vary"] = ", ".join(parts)
            else:
                resp.headers["vary"] = "Accept"
            return resp

        # 7. Default to 404 for non-HTML or unknown routes
        raise HTTPException(status_code=404, detail="Not Found")


def create_web_delivery_test_app(
    dist_dir: Path,
    web_dir: Optional[Path] = None,
    public_dir: Optional[Path] = None,
) -> FastAPI:
    """Create an isolated, lightweight FastAPI test app with web delivery routes."""
    test_app = FastAPI(title="Web Delivery Test App")
    handler = WebDeliveryHandler(dist_dir=dist_dir, web_dir=web_dir, public_dir=public_dir)

    def merge_vary_accept(resp: Response) -> Response:
        v = resp.headers.get("vary")
        if v:
            parts = [p.strip() for p in v.split(",")]
            if "Accept" not in parts:
                parts.append("Accept")
            resp.headers["vary"] = ", ".join(parts)
        else:
            resp.headers["vary"] = "Accept"
        return resp

    @test_app.api_route("/films/{movie_id}", methods=["GET", "HEAD"])
    async def get_film(movie_id: str, request: Request):
        if is_html_requested(request):
            return merge_vary_accept(handler.serve_index_html(request))
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"ENDPOINT_GONE: Legacy /films/{movie_id} is deprecated. Use GET /api/v1/catalog/works/{movie_id}.",
            headers={"Vary": "Accept"}
        )

    @test_app.api_route("/films/{movie_id}/reveals", methods=["GET", "HEAD"])
    async def get_film_reveals(movie_id: str, request: Request):
        if is_html_requested(request):
            return merge_vary_accept(handler.serve_index_html(request))
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"ENDPOINT_GONE: Legacy /films/{movie_id}/reveals is deprecated. Use GET /api/v1/catalog/works/{movie_id}/reveals.",
            headers={"Vary": "Accept"}
        )

    @test_app.api_route("/styles.css", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_styles(request: Request):
        return handler.serve_styles(request)

    @test_app.api_route("/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_asset(asset_path: str, request: Request):
        return handler.serve_asset(asset_path, request)

    @test_app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_index(request: Request):
        return handler.serve_index_html(request)

    @test_app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa_or_asset(full_path: str, request: Request):
        return handler.handle_spa_or_asset(full_path, request)

    return test_app
