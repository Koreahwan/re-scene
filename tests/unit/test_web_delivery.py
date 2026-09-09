"""
Standalone unit test suite for apps/api/web_delivery.py.
Pure isolated testing without importing apps.api.main, Settings, Database, or Redis.
Can be executed directly with:
    python -I -B tests/unit/test_web_delivery.py
or via pytest without modifying tests/conftest.py.
"""
from __future__ import annotations

import ast
import asyncio
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import httpx
from fastapi import Request, HTTPException

# Locate repo root and load web_delivery dynamically without importing apps.api.main
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "apps" / "api" / "web_delivery.py"

spec = importlib.util.spec_from_file_location("web_delivery_module", MODULE_PATH)
web_delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_delivery)

WebDeliveryHandler = web_delivery.WebDeliveryHandler
BoundedStaticFileCache = web_delivery.BoundedStaticFileCache
StaticFileCacheEntry = web_delivery.StaticFileCacheEntry
create_web_delivery_test_app = web_delivery.create_web_delivery_test_app
is_html_requested = web_delivery.is_html_requested
is_gzip_accepted = web_delivery.is_gzip_accepted
is_fingerprinted_asset = web_delivery.is_fingerprinted_asset
is_compressible_type = web_delivery.is_compressible_type
is_safe_relative_path = web_delivery.is_safe_relative_path


class TestWebDeliveryStandalone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test directory within custom tmp if provided
        custom_tmp = os.environ.get("REFRAME_TEST_TMP")
        if custom_tmp and not Path(custom_tmp).exists():
            Path(custom_tmp).mkdir(parents=True, exist_ok=True)
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="web-delivery-test-", dir=custom_tmp)
        cls.root = Path(cls.temp_dir.name)
        cls.web_dir = cls.root / "web"
        cls.dist_dir = cls.web_dir / "dist"
        cls.dist_assets_dir = cls.dist_dir / "assets"
        cls.public_dir = cls.web_dir / "public"
        cls.public_assets_dir = cls.public_dir / "assets"

        cls.dist_assets_dir.mkdir(parents=True, exist_ok=True)
        cls.public_assets_dir.mkdir(parents=True, exist_ok=True)

        cls.index_content = b"<!DOCTYPE html><html><head><title>Reframe Test</title></head><body><div id='root'></div></body></html>"
        (cls.dist_dir / "index.html").write_bytes(cls.index_content)

        # Synthetic test assets with dummy hashes (independent of local build)
        cls.js_raw = b"console.log('Reframe unit test bundle');\n" * 100
        cls.css_raw = b".reframe-box { color: #ffffff; background: #000000; }\n" * 50
        (cls.dist_assets_dir / "index-AbCd1234.js").write_bytes(cls.js_raw)
        (cls.dist_assets_dir / "index-CGzY8SeH.css").write_bytes(cls.css_raw)

        # Non-fingerprinted, non-compressible PNG
        cls.png_raw = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        (cls.dist_assets_dir / "poster-fixed.png").write_bytes(cls.png_raw)

        # styles.css
        cls.styles_raw = b"body { margin: 0; }\n" * 20
        (cls.web_dir / "styles.css").write_bytes(cls.styles_raw)

        # Sentinel files outside/inside for traversal tests
        (cls.web_dir / "package.json").write_bytes(b'{"name": "test-sentinel"}')
        (cls.web_dir / "tsconfig.json").write_bytes(b'{}')
        (cls.web_dir / ".env").write_bytes(b"TEST_SECRET=1")
        (cls.dist_assets_dir / "index.js.map").write_bytes(b'{}')

        # Outside folder for symlink escape test
        cls.outside_dir = cls.root / "outside"
        cls.outside_dir.mkdir()
        (cls.outside_dir / "safe-sentinel.css").write_bytes(b"OUTSIDE_SENTINEL_CONTENT")

        cls.app = create_web_delivery_test_app(
            dist_dir=cls.dist_dir,
            web_dir=cls.web_dir,
            public_dir=cls.public_dir,
        )
        cls.handler = WebDeliveryHandler(
            dist_dir=cls.dist_dir,
            web_dir=cls.web_dir,
            public_dir=cls.public_dir,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Pure Unit Functions
    # -------------------------------------------------------------

    def test_pure_fingerprinted_asset(self):
        self.assertTrue(is_fingerprinted_asset("index-AbCd1234.js"))
        self.assertTrue(is_fingerprinted_asset("index-CGzY8SeH.css"))
        self.assertFalse(is_fingerprinted_asset("poster-fixed.png"))
        self.assertFalse(is_fingerprinted_asset("styles.css"))
        self.assertFalse(is_fingerprinted_asset("index.html"))

    def test_pure_compressible_type(self):
        self.assertTrue(is_compressible_type("application/javascript", "bundle.js"))
        self.assertTrue(is_compressible_type("text/css", "styles.css"))
        self.assertTrue(is_compressible_type("text/html", "index.html"))
        self.assertTrue(is_compressible_type("image/svg+xml", "icon.svg"))
        self.assertFalse(is_compressible_type("image/png", "img.png"))
        self.assertFalse(is_compressible_type("image/jpeg", "img.jpg"))
        self.assertFalse(is_compressible_type("video/mp4", "vid.mp4"))

    def test_pure_safe_relative_path(self):
        self.assertTrue(is_safe_relative_path("assets/index-AbCd1234.js"))
        self.assertTrue(is_safe_relative_path("styles.css"))
        self.assertFalse(is_safe_relative_path("../package.json"))
        self.assertFalse(is_safe_relative_path("assets/../../package.json"))
        self.assertFalse(is_safe_relative_path("%2e%2e/package.json"))
        self.assertFalse(is_safe_relative_path("assets\\test.js"))
        self.assertFalse(is_safe_relative_path(".env"))
        self.assertFalse(is_safe_relative_path("package.json"))
        self.assertFalse(is_safe_relative_path("tsconfig.json"))
        self.assertFalse(is_safe_relative_path("src/App.tsx"))
        self.assertFalse(is_safe_relative_path("assets/index.js.map"))

    # -------------------------------------------------------------
    # 2. HTTP ETag & Representation Contracts
    # -------------------------------------------------------------

    def test_representation_etags_differ(self):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                identity_resp = await client.get("/assets/index-AbCd1234.js", headers={"Accept-Encoding": "identity"})
                gzip_resp = await client.get("/assets/index-AbCd1234.js", headers={"Accept-Encoding": "gzip"})

                # Both representations must succeed
                self.assertEqual(identity_resp.status_code, 200)
                self.assertEqual(gzip_resp.status_code, 200)

                id_etag = identity_resp.headers.get("etag")
                gz_etag = gzip_resp.headers.get("etag")

                # Must not return the exact same strong ETag
                self.assertNotEqual(id_etag, gz_etag)
                self.assertTrue(id_etag.startswith('"') and not id_etag.startswith("W/"))
                self.assertTrue(gz_etag.startswith("W/"))
        asyncio.run(run())

    def test_if_none_match_weak_comparison(self):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/assets/index-AbCd1234.js")
                etag = resp.headers["etag"]
                raw_hash = etag.strip('"').lstrip("W/").strip('"')

                # Matching with weak tag
                resp_304_w = await client.get("/assets/index-AbCd1234.js", headers={"If-None-Match": f'W/"{raw_hash}"'})
                self.assertEqual(resp_304_w.status_code, 304)
                self.assertEqual(resp_304_w.content, b"")

                # Matching with strong tag
                resp_304_s = await client.get("/assets/index-AbCd1234.js", headers={"If-None-Match": f'"{raw_hash}"'})
                self.assertEqual(resp_304_s.status_code, 304)
                self.assertEqual(resp_304_s.content, b"")
        asyncio.run(run())

    def test_if_range_mismatch_and_match(self):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                raw_hash = hashlib.sha256(self.js_raw).hexdigest()[:16]

                # 1. Mismatched If-Range MUST return full 200 OK (not 206)
                mismatch_resp = await client.get(
                    "/assets/index-AbCd1234.js",
                    headers={"Range": "bytes=0-5", "If-Range": '"wrong-version"'}
                )
                self.assertEqual(mismatch_resp.status_code, 200)
                self.assertEqual(len(mismatch_resp.content), len(self.js_raw))

                # 2. Weak If-Range MUST return full 200 OK (RFC 9110 § 13.1.5: If-Range requires strong comparison)
                weak_resp = await client.get(
                    "/assets/index-AbCd1234.js",
                    headers={"Range": "bytes=0-5", "If-Range": f'W/"{raw_hash}"'}
                )
                self.assertEqual(weak_resp.status_code, 200)
                self.assertEqual(len(weak_resp.content), len(self.js_raw))

                # 3. Matched strong If-Range MUST return 206 Partial Content (uncompressed)
                match_resp = await client.get(
                    "/assets/index-AbCd1234.js",
                    headers={"Range": "bytes=0-5", "If-Range": f'"{raw_hash}"'}
                )
                self.assertEqual(match_resp.status_code, 206)
                self.assertEqual(match_resp.headers.get("content-range"), f"bytes 0-5/{len(self.js_raw)}")
                self.assertNotIn("content-encoding", match_resp.headers)
                self.assertEqual(match_resp.content, self.js_raw[0:6])
        asyncio.run(run())

    # -------------------------------------------------------------
    # 3. SPA Routing & HTML Caching Contract
    # -------------------------------------------------------------

    def test_reset_password_route_and_index_html_no_cache(self):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                # /reset-password route
                resp_reset = await client.get("/reset-password", headers={"Accept": "text/html"})
                self.assertEqual(resp_reset.status_code, 200)
                self.assertIn("text/html", resp_reset.headers["content-type"])
                self.assertEqual(resp_reset.headers.get("cache-control"), "no-cache")

                # /forgot-password route
                resp_forgot = await client.get("/forgot-password", headers={"Accept": "text/html"})
                self.assertEqual(resp_forgot.status_code, 200)
                self.assertEqual(resp_forgot.headers.get("cache-control"), "no-cache")

                # Direct navigation to Notice must serve the application shell.
                resp_notice = await client.get("/notice", headers={"Accept": "text/html"})
                self.assertEqual(resp_notice.status_code, 200)
                self.assertIn("text/html", resp_notice.headers["content-type"])
                self.assertEqual(resp_notice.headers.get("cache-control"), "no-cache")

                # Bookmarked box-office film information must survive a reload.
                resp_box_office = await client.get(
                    "/box-office/film?title=The%20Odyssey", headers={"Accept": "text/html"}
                )
                self.assertEqual(resp_box_office.status_code, 200)
                self.assertIn("text/html", resp_box_office.headers["content-type"])
                self.assertEqual(resp_box_office.headers.get("cache-control"), "no-cache")

                # /index.html direct access must be no-cache (never max-age=3600)
                resp_index = await client.get("/index.html", headers={"Accept": "text/html"})
                self.assertEqual(resp_index.status_code, 200)
                self.assertEqual(resp_index.headers.get("cache-control"), "no-cache")

                # /assets/index.html must return 404
                resp_assets_index = await client.get("/assets/index.html")
                self.assertEqual(resp_assets_index.status_code, 404)
        asyncio.run(run())

    def test_film_route_html_vs_legacy_410_and_vary_accept(self):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                # HTML request -> 200 OK HTML with Vary: Accept merged
                resp_html = await client.get(
                    "/films/the-bat-whispers-1930",
                    headers={"Accept": "text/html,application/xhtml+xml"}
                )
                self.assertEqual(resp_html.status_code, 200)
                self.assertIn("text/html", resp_html.headers["content-type"])
                vary = resp_html.headers.get("vary", "")
                self.assertIn("Accept", vary)

                # Legacy API request -> 410 GONE with Vary: Accept
                resp_api = await client.get(
                    "/films/the-bat-whispers-1930",
                    headers={"Accept": "application/json"}
                )
                self.assertEqual(resp_api.status_code, 410)
                self.assertIn("Accept", resp_api.headers.get("vary", ""))

                # q=0 HTML -> 410 GONE
                resp_q0 = await client.get(
                    "/films/the-bat-whispers-1930",
                    headers={"Accept": "text/html;q=0, application/json"}
                )
                self.assertEqual(resp_q0.status_code, 410)

                # Film reveals deep-link HTML
                resp_deep = await client.get(
                    "/films/the-bat-whispers-1930/reveals/reveal-anderson-identity",
                    headers={"Accept": "text/html"}
                )
                self.assertEqual(resp_deep.status_code, 200)
                self.assertIn("text/html", resp_deep.headers["content-type"])
        asyncio.run(run())

    # -------------------------------------------------------------
    # 4. File Boundaries & Symlink Protection
    # -------------------------------------------------------------

    def test_boundary_escaped_path_handler_unit_verification(self):
        """
        Deterministic unit verification:
        - _resolve_file returns None when a candidate resolves outside allowed roots.
        - Public handlers (serve_styles, serve_index_html, serve_asset) raise HTTPException(404)
          when target files resolve outside roots or fail containment.
        """
        # 1. Direct containment check
        outside_file = self.outside_dir / "safe-sentinel.css"
        self.assertFalse(
            web_delivery.is_contained_in_roots(outside_file.resolve(), [self.dist_dir, self.web_dir])
        )

        # 2. _resolve_file contract: returns None for non-existent, unsafe, forbidden, or outside paths
        self.assertIsNone(self.handler._resolve_file("../outside/safe-sentinel.css"))
        self.assertIsNone(self.handler._resolve_file("package.json"))
        self.assertIsNone(self.handler._resolve_file(".env"))

        # 3. Handlers raise 404 when candidate file resolves outside allowed roots
        req = Request({"type": "http", "method": "GET", "path": "/styles.css", "headers": []})
        with mock.patch.object(web_delivery, "is_contained_in_roots", return_value=False):
            # serve_styles
            with self.assertRaises(HTTPException) as cm_styles:
                self.handler.serve_styles(req)
            self.assertEqual(cm_styles.exception.status_code, 404)

            # serve_index_html
            with self.assertRaises(HTTPException) as cm_index:
                self.handler.serve_index_html(req)
            self.assertEqual(cm_index.exception.status_code, 404)

            # serve_asset
            with self.assertRaises(HTTPException) as cm_asset:
                self.handler.serve_asset("index-AbCd1234.js", req)
            self.assertEqual(cm_asset.exception.status_code, 404)

    def test_os_symlink_escape_verification(self):
        """
        Platform OS symlink test:
        Attempts to create an actual filesystem symlink to an outside sentinel.
        If unsupported or unprivileged on current OS, explicitly records skip.
        If supported, verifies _resolve_file returns None and handlers raise 404.
        """
        sym_path = self.web_dir / "styles-sym.css"
        try:
            if sym_path.exists():
                sym_path.unlink()
            sym_path.symlink_to(self.outside_dir / "safe-sentinel.css")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"OS symlink creation unsupported or unprivileged on current platform: {exc}")

        try:
            # 1. _resolve_file contract: must return None (never raise HTTPException)
            resolved = self.handler._resolve_file("styles-sym.css")
            self.assertIsNone(resolved)

            # 2. Handler boundary enforcement: serve_styles with symlinked file raises 404
            escaped_dir = self.root / "escaped_web"
            escaped_dir.mkdir(exist_ok=True)
            escaped_styles = escaped_dir / "styles.css"
            if escaped_styles.exists():
                escaped_styles.unlink()
            escaped_styles.symlink_to(self.outside_dir / "safe-sentinel.css")

            req = Request({"type": "http", "method": "GET", "path": "/styles.css", "headers": []})
            handler = WebDeliveryHandler(dist_dir=self.dist_dir, web_dir=escaped_dir)
            with self.assertRaises(HTTPException) as cm:
                handler.serve_styles(req)
            self.assertEqual(cm.exception.status_code, 404)
        finally:
            if sym_path.exists():
                sym_path.unlink()

    # -------------------------------------------------------------
    # 5. Static AST Verification of apps/api/main.py
    # -------------------------------------------------------------

    def test_main_py_static_ast_verification(self):
        main_py_path = REPO_ROOT / "apps" / "api" / "main.py"
        self.assertTrue(main_py_path.exists(), "apps/api/main.py must exist")

        source = main_py_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename="apps/api/main.py")

        # 1. Verify NO wholesale app.mount("/static", ...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "mount":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and arg.value == "/static":
                            self.fail("apps/api/main.py must not contain app.mount('/static', ...)")

        # 2. Verify web_delivery instantiation and route registrations
        self.assertIn("from apps.api.web_delivery import WebDeliveryHandler, is_html_requested", source)
        self.assertIn('@app.api_route("/films/{movie_id}"', source)
        self.assertIn('@app.api_route("/films/{movie_id}/reveals"', source)
        self.assertIn('@app.api_route("/styles.css"', source)
        self.assertIn('@app.api_route("/assets/{asset_path:path}"', source)
        self.assertIn('@app.api_route("/"', source)
        self.assertIn('@app.api_route("/{full_path:path}"', source)

        # Record static-only verification
        self.verification_metadata = {
            "main_py_ast_verified": True,
            "main_py_live_execution": "NOT_EXECUTED (static AST verified to preserve isolation)",
        }

    # -------------------------------------------------------------
    # 6. In-Memory Bounded Static Cache Verification
    # -------------------------------------------------------------

    def test_static_file_cache_reuse_and_invalidation(self):
        """
        Verify:
        - Cache hit reuses raw_content, raw_hash, and precomputed gzip_content.
        - Modifying the file on disk (mtime/size change) invalidates the cache immediately.
        """
        test_file = self.dist_assets_dir / "cache-test.js"
        initial_bytes = b"console.log('v1');\n" * 50
        test_file.write_bytes(initial_bytes)

        cache = BoundedStaticFileCache(max_entries=10, max_retained_bytes=1024 * 1024)
        handler = WebDeliveryHandler(dist_dir=self.dist_dir, web_dir=self.web_dir)
        handler.file_cache = cache

        req_ident = Request({"type": "http", "method": "GET", "path": "/assets/cache-test.js", "headers": []})
        req_gzip = Request({
            "type": "http",
            "method": "GET",
            "path": "/assets/cache-test.js",
            "headers": [(b"accept-encoding", b"gzip")]
        })

        # 1. First request populates raw cache
        resp1 = handler.build_file_response(test_file, req_ident)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(cache.stats["entries"], 1)
        entry1 = cache.get(test_file)
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.raw_content, initial_bytes)
        self.assertIsNone(entry1.gzip_content)

        # 2. Second request with gzip attaches gzip representation
        resp2 = handler.build_file_response(test_file, req_gzip)
        self.assertEqual(resp2.status_code, 200)
        entry2 = cache.get(test_file)
        self.assertIsNotNone(entry2)
        self.assertIsNotNone(entry2.gzip_content)
        self.assertEqual(gzip.decompress(entry2.gzip_content), initial_bytes)

        # 3. Third request reuses cached entry without disk re-read
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("Should not read disk on cache hit")):
            resp3 = handler.build_file_response(test_file, req_gzip)
            self.assertEqual(resp3.status_code, 200)

        # 4. Modify file on disk -> cache must invalidate on next request
        updated_bytes = b"console.log('v2-updated');\n" * 100
        import time
        time.sleep(0.01)  # ensure mtime differs
        test_file.write_bytes(updated_bytes)

        resp4 = handler.build_file_response(test_file, req_ident)
        self.assertEqual(resp4.status_code, 200)
        self.assertEqual(resp4.body, updated_bytes)
        entry_updated = cache.get(test_file)
        self.assertIsNotNone(entry_updated)
        self.assertEqual(entry_updated.raw_content, updated_bytes)

    def test_static_file_cache_eviction_and_bypass(self):
        """
        Verify:
        - Over-capacity inserts trigger LRU eviction.
        - Files exceeding max_single_file_bytes bypass the cache without error.
        """
        # Cache with tiny bounds: max 2 entries, max 1000 bytes, max 400 bytes per single file
        cache = BoundedStaticFileCache(max_entries=2, max_retained_bytes=1000, max_single_file_bytes=400)

        p1 = self.dist_assets_dir / "item1.js"
        p2 = self.dist_assets_dir / "item2.js"
        p3 = self.dist_assets_dir / "item3.js"
        oversized = self.dist_assets_dir / "oversized.js"

        p1.write_bytes(b"A" * 100)
        p2.write_bytes(b"B" * 100)
        p3.write_bytes(b"C" * 100)
        oversized.write_bytes(b"X" * 500)

        cache.put(p1, p1.stat().st_mtime_ns, p1.stat().st_size, b"A" * 100, "hashA")
        cache.put(p2, p2.stat().st_mtime_ns, p2.stat().st_size, b"B" * 100, "hashB")
        self.assertEqual(cache.stats["entries"], 2)

        # Access p1 to make p2 the LRU item
        cache.get(p1)

        # Insert p3 -> should evict p2 (LRU)
        cache.put(p3, p3.stat().st_mtime_ns, p3.stat().st_size, b"C" * 100, "hashC")
        self.assertEqual(cache.stats["entries"], 2)
        self.assertIsNotNone(cache.get(p1))
        self.assertIsNone(cache.get(p2))
        self.assertIsNotNone(cache.get(p3))

        # Oversized file bypasses cache
        res = cache.put(oversized, 4, 500, b"X" * 500, "hashX")
        self.assertIsNone(res)
        self.assertIsNone(cache.get(oversized))
        self.assertEqual(cache.stats["entries"], 2)

    def test_static_file_cache_stale_update_rejected(self):
        """
        Verify:
        - When entry A is replaced by entry B, update_gzip with expected_entry=A or expected_raw_hash=hashA
          is rejected (returns None) and does NOT corrupt entry B with A's stale gzip content.
        """
        cache = BoundedStaticFileCache(max_entries=10, max_retained_bytes=1000)
        p = self.dist_assets_dir / "race.js"
        p.write_bytes(b"content-v1")

        st_a = p.stat()
        entry_a = cache.put(p, st_a.st_mtime_ns, st_a.st_size, b"content-v1", "hash-v1")
        self.assertIsNotNone(entry_a)
        self.assertIsNone(entry_a.gzip_content)

        # Simulate replacement by entry B
        import time
        time.sleep(0.01)
        p.write_bytes(b"content-v2-new")
        st_b = p.stat()
        entry_b = cache.put(p, st_b.st_mtime_ns, st_b.st_size, b"content-v2-new", "hash-v2")
        self.assertIsNotNone(entry_b)
        self.assertIsNot(entry_a, entry_b)

        # Stale update from slow worker compressing A
        stale_gzip = gzip.compress(b"content-v1")
        res_stale = cache.update_gzip(p, stale_gzip, expected_entry=entry_a, expected_raw_hash="hash-v1")
        self.assertIsNone(res_stale)

        # Verify entry_b remains intact and uncontaminated
        current = cache.get(p)
        self.assertIs(current, entry_b)
        self.assertIsNone(current.gzip_content)

        # Valid update for entry B succeeds
        valid_gzip = gzip.compress(b"content-v2-new")
        res_valid = cache.update_gzip(p, valid_gzip, expected_entry=entry_b, expected_raw_hash="hash-v2")
        self.assertIsNotNone(res_valid)
        self.assertEqual(res_valid.gzip_content, valid_gzip)

    def test_static_file_cache_update_gzip_caps_and_budget(self):
        """
        Verify:
        - Combined raw + gzip exceeding max_single_file_bytes leaves raw in cache but rejects gzip addition.
        - update_gzip evicts other LRU entries when needed to satisfy max_retained_bytes global budget.
        """
        # max 2 entries, max 30 bytes retained, max 20 bytes per single file
        cache = BoundedStaticFileCache(max_entries=2, max_retained_bytes=30, max_single_file_bytes=20)

        p1 = self.dist_assets_dir / "cap1.js"
        p2 = self.dist_assets_dir / "cap2.js"

        p1.write_bytes(b"A" * 10)
        st1 = p1.stat()

        # 1. Test combined single file cap: raw=10, gzip=15 -> combined=25 > 20
        cache.put(p1, st1.st_mtime_ns, st1.st_size, b"A" * 10, "hashA")
        entry1 = cache.get(p1)
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.retained_bytes, 10)

        # Attempt to add 15 bytes gzip
        cache.update_gzip(p1, b"G" * 15, expected_entry=entry1)
        # Gzip rejected because 10 + 15 = 25 > 20 (max_single_file_bytes)
        self.assertIsNone(entry1.gzip_content)
        self.assertEqual(entry1.retained_bytes, 10)
        self.assertLessEqual(entry1.retained_bytes, 20)

        # 2. Test global budget eviction during update_gzip:
        # Put p2 (10 bytes) -> total retained = 20 <= 30
        p2.write_bytes(b"B" * 10)
        st2 = p2.stat()
        cache.put(p2, st2.st_mtime_ns, st2.st_size, b"B" * 10, "hashB")
        entry2 = cache.get(p2)
        self.assertIsNotNone(entry2)
        self.assertEqual(cache.stats["retained_bytes"], 20)
        self.assertEqual(cache.stats["entries"], 2)

        # Add 10 bytes gzip to p2 -> combined for p2 is 20 <= 20, total fits in 30
        cache.update_gzip(p2, b"Z" * 10, expected_entry=entry2)
        self.assertIsNotNone(entry2.gzip_content)
        self.assertEqual(cache.stats["retained_bytes"], 30)

        # 3. Add p3 (8 bytes) -> total would be 38 > 30, evicts LRU (p1)
        p3 = self.dist_assets_dir / "cap3.js"
        p3.write_bytes(b"C" * 8)
        st3 = p3.stat()
        cache.put(p3, st3.st_mtime_ns, st3.st_size, b"C" * 8, "hashC")
        self.assertLessEqual(cache.stats["retained_bytes"], 30)
        self.assertIsNone(cache.get(p1))  # p1 evicted
        self.assertIsNotNone(cache.get(p2))  # p2 kept


if __name__ == "__main__":
    unittest.main()
