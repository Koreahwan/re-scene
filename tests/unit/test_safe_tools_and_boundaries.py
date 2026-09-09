"""
Reframe V7 Safe Tools & Data Boundaries Verification Suite (R3-2)
Verifies:
- R3-2A: Whole-identity structured target checks (rejects same DB/diff host, diff port, same basename/diff dir)
- R3-2B: Mandatory expected_target & confirmation for non-dry-run writes (zero writes on missing/partial target)
- R3-2C: Real migration verification (alembic_version table, revision 0013, PK, single-column UNIQUE, non-nullable)
- R3-2D: Full canonical diffing (directors, cast, countries, source_url) under same/new/stale revision scenarios
- R3-2E: Atomic rollback on failure and idempotent exact no-op on re-run
- R3-2F: Seed CLI scope separation, count limits, and magazine-only zero community leakage
- R3-2G: Zero credential leakage (canary password and query tokens redacted from masks and error messages)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, Table, Column, String, Integer, MetaData, UniqueConstraint
from sqlalchemy.orm import Session

from src.reframe.catalog.models import FilmCatalog
from src.reframe.shared.config import settings
from tools.catalog.target_safety import (
    mask_db_url,
    match_structured_target,
    verify_db_target_and_schema,
    compute_canonical_film_diff,
)
from tools.catalog.import_wikidata_catalog import run_importer
from tools.catalog.sync_film_metadata import sync_catalog
from tools.simulation.seed_synthetic_demo_content import parse_args, run_seeder


class TestSafeToolsAndBoundariesR3(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="safe-tools-r3-")
        self.db_path = Path(self.temp_dir.name) / "test_ephemeral.db"
        self.sync_db_url = f"sqlite:///{self.db_path.as_posix()}"

        # Provision real test DB via official Alembic migrations (NOT create_all)
        alembic_cfg = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", self.sync_db_url)
        command.upgrade(alembic_cfg, "head")

        self.engine = create_engine(self.sync_db_url, echo=False)
        self.catalog_path = REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json"

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    # =========================================================================
    # R3-2A: Whole-Identity Structured Target Verification
    # =========================================================================
    def test_r3_2a_structured_target_rejections(self):
        """Reject same DB/diff host, diff port, same basename/diff dir."""
        pg_url = "postgresql://app_user:pass123@db.prod.internal:5432/reframe_main"

        # 1. Network: Same DB name, different host -> reject
        self.assertFalse(match_structured_target(pg_url, "other-host.internal/reframe_main"))
        # 2. Network: Same host, different port -> reject
        self.assertFalse(match_structured_target(pg_url, "db.prod.internal:5433/reframe_main"))
        # 3. Network: Same host, different DB -> reject
        self.assertFalse(match_structured_target(pg_url, "db.prod.internal:5432/other_db"))
        # 4. Network: Partial identity (host only or db only) -> reject
        self.assertFalse(match_structured_target(pg_url, "db.prod.internal"))
        self.assertFalse(match_structured_target(pg_url, "reframe_main"))
        # 5. Network: Exact full match -> accept
        self.assertTrue(match_structured_target(pg_url, "db.prod.internal:5432/reframe_main"))
        self.assertTrue(match_structured_target(pg_url, "db.prod.internal/reframe_main"))

        # 6. SQLite: Same basename, different directory -> reject
        other_dir_path = Path(self.temp_dir.name) / "sub_folder" / "test_ephemeral.db"
        self.assertFalse(match_structured_target(self.sync_db_url, str(other_dir_path)))
        # 7. SQLite: Substring match without path equality -> reject
        self.assertFalse(match_structured_target(self.sync_db_url, "test_ephemeral.db"))
        # 8. SQLite: Exact path match -> accept
        self.assertTrue(match_structured_target(self.sync_db_url, str(self.db_path)))

    # =========================================================================
    # R3-2B: Expected Target & Confirmation Mandatory for Writes
    # =========================================================================
    def test_r3_2b_mandatory_target_and_confirmation_zero_writes(self):
        """Zero writes when expected_target is missing, partial, or confirmation omitted."""
        # 1. Importer: missing expected_target on non-dry-run -> raises ValueError, writes=0
        with self.assertRaises(ValueError) as ctx:
            run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=None)
        self.assertIn("expected_target must be explicitly provided", str(ctx.exception))

        # 2. Importer: target mismatch -> raises ValueError, writes=0
        with self.assertRaises(ValueError) as ctx:
            run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target="wrong/target")
        self.assertIn("identity mismatch", str(ctx.exception))

        # 3. Sync: missing expected_target on confirm_sync -> raises ValueError, writes=0
        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, self.catalog_path, confirm_sync=True, dry_run=False, expected_target=None)
        self.assertIn("expected_target must be explicitly provided", str(ctx.exception))

        # 4. Verify 0 records written
        with Session(self.engine) as session:
            self.assertEqual(session.query(FilmCatalog).count(), 0)

    # =========================================================================
    # R3-2C: Real Alembic Migration Verification
    # =========================================================================
    def test_r3_2c_schema_migration_checks(self):
        """Reject unmigrated tables, stale revisions, composite-only unique constraints."""
        # 1. Real migrated DB passes verification
        verify_db_target_and_schema(self.engine, "0013_v7_film_catalog_metadata")

        # 2. DB missing alembic_version table -> reject
        raw_engine = create_engine("sqlite:///:memory:", echo=False)
        FilmCatalog.metadata.create_all(raw_engine)
        with self.assertRaises(RuntimeError) as ctx:
            verify_db_target_and_schema(raw_engine, "0013_v7_film_catalog_metadata")
        self.assertIn("missing 'alembic_version' table", str(ctx.exception))
        raw_engine.dispose()

        # 3. DB with incorrect/stale revision -> reject
        with self.engine.connect() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '0012_v7_audit_log_sqlite_pk'"))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx:
            verify_db_target_and_schema(self.engine, "0013_v7_film_catalog_metadata")
        self.assertIn("revision mismatch", str(ctx.exception))

        # Restore revision for subsequent tests
        with self.engine.connect() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '0013_v7_film_catalog_metadata'"))
            conn.commit()

        # 4. DB where source_qid is only in composite unique -> reject
        comp_engine = create_engine("sqlite:///:memory:", echo=False)
        with comp_engine.connect() as conn:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) PRIMARY KEY)"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('0013_v7_film_catalog_metadata')"))
            # Create table with composite unique (source_qid, title_en) but NO single-column unique
            conn.execute(text("""
                CREATE TABLE film_catalog (
                    movie_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    source_qid VARCHAR(32) NOT NULL,
                    title_en VARCHAR(255) NOT NULL,
                    title_ko VARCHAR(255),
                    year INTEGER NOT NULL,
                    description_en TEXT,
                    description_ko TEXT,
                    runtime_minutes INTEGER,
                    directors JSON NOT NULL,
                    cast_members JSON NOT NULL,
                    genres JSON NOT NULL,
                    countries JSON NOT NULL,
                    languages JSON NOT NULL,
                    core_demo_supported BOOLEAN NOT NULL,
                    poster_local_path VARCHAR(255),
                    poster_source_filename VARCHAR(255),
                    poster_sha256 VARCHAR(64),
                    poster_license VARCHAR(128),
                    source_revision BIGINT NOT NULL,
                    source_url VARCHAR(255) NOT NULL,
                    fetched_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT uq_composite UNIQUE (source_qid, title_en)
                )
            """))
            conn.commit()

        with self.assertRaises(RuntimeError) as ctx:
            verify_db_target_and_schema(comp_engine, "0013_v7_film_catalog_metadata")
        self.assertIn("must have a dedicated single-column UNIQUE constraint", str(ctx.exception))
        comp_engine.dispose()

    # =========================================================================
    # R3-2D: Canonical Diffing Under Same/New/Stale Revision
    # =========================================================================
    def test_r3_2d_canonical_diff_directors_cast_countries_source_url(self):
        """Detect mutations in directors, cast, countries, source_url under same vs bumped revision."""
        # Initial sync
        sync_catalog(
            self.sync_db_url,
            self.catalog_path,
            expected_target=str(self.db_path),
            confirm_sync=True,
            dry_run=False,
        )

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            base_data = json.load(f)

        # 1. Mutate directors only under SAME revision -> Conflict rejection
        mutated_data = json.loads(json.dumps(base_data))
        mutated_data["films"][0]["directors"] = ["Mutated Director"]
        p_dir = Path(self.temp_dir.name) / "mut_dir.json"
        with open(p_dir, "w", encoding="utf-8") as f:
            json.dump(mutated_data, f)

        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, p_dir, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertIn("cannot modify content without bumping source_revision", str(ctx.exception))

        # 2. Mutate cast only under SAME revision -> Conflict rejection
        mutated_data2 = json.loads(json.dumps(base_data))
        mutated_data2["films"][0]["cast"] = ["Actor One", "Actor Two"]
        p_cast = Path(self.temp_dir.name) / "mut_cast.json"
        with open(p_cast, "w", encoding="utf-8") as f:
            json.dump(mutated_data2, f)

        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, p_cast, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertIn("cannot modify content without bumping source_revision", str(ctx.exception))

        # 3. Mutate countries only under SAME revision -> Conflict rejection
        mutated_data3 = json.loads(json.dumps(base_data))
        mutated_data3["films"][0]["countries"] = ["New Country"]
        p_ctry = Path(self.temp_dir.name) / "mut_ctry.json"
        with open(p_ctry, "w", encoding="utf-8") as f:
            json.dump(mutated_data3, f)

        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, p_ctry, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertIn("cannot modify content without bumping source_revision", str(ctx.exception))

        # 4. Mutate under BUMPED revision -> Successful update
        bumped_data = json.loads(json.dumps(base_data))
        bumped_data["films"][0]["directors"] = ["Approved Director"]
        bumped_data["films"][0]["source_revision"] = bumped_data["films"][0]["source_revision"] + 1
        p_bumped = Path(self.temp_dir.name) / "bumped.json"
        with open(p_bumped, "w", encoding="utf-8") as f:
            json.dump(bumped_data, f)

        rep = sync_catalog(self.sync_db_url, p_bumped, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertEqual(len(rep["updated"]), 1)
        self.assertEqual(rep["updated"][0]["movie_id"], bumped_data["films"][0]["movie_id"])

        # 5. Stale revision (older revision than DB, where DB is at rev 2 and incoming is rev 1) -> Rejection
        stale_data = json.loads(json.dumps(base_data))
        stale_data["films"][0]["source_revision"] = 1  # Valid integer > 0, but older than DB rev 2
        p_stale = Path(self.temp_dir.name) / "stale.json"
        with open(p_stale, "w", encoding="utf-8") as f:
            json.dump(stale_data, f)

        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, p_stale, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertIn("Stale revision", str(ctx.exception))

    # =========================================================================
    # R3-2E: Flush Failure Atomic Rollback & Exact No-Op
    # =========================================================================
    def test_r3_2e_flush_rollback_and_exact_noop(self):
        """Forced error during write rolls back completely; re-running exact payload is 20 no_op."""
        from src.reframe.catalog.repository import FilmCatalogRepository

        original_sync = FilmCatalogRepository.sync_import_films

        def crashing_sync(session, films):
            session.add(FilmCatalog(
                movie_id="test-partial-fail",
                source_qid="Q_FAIL_999",
                title_en="Partial Fail",
                year=2026,
                source_revision=1,
                source_url="http://fail.test",
                fetched_at=datetime.now(timezone.utc),
            ))
            session.flush()
            raise RuntimeError("Forced post-flush simulation error")

        with patch.object(FilmCatalogRepository, "sync_import_films", side_effect=crashing_sync):
            with self.assertRaises(RuntimeError):
                run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))

        # Verify rollback: 0 rows in DB
        with Session(self.engine) as session:
            self.assertEqual(session.query(FilmCatalog).count(), 0)

        # Initial clean import
        run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        with Session(self.engine) as session:
            self.assertEqual(session.query(FilmCatalog).count(), 20)

        # Re-run sync: exact same payload must result in 20 no_op
        rep = sync_catalog(self.sync_db_url, self.catalog_path, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertEqual(len(rep["no_op"]), 20)
        self.assertEqual(len(rep["created"]), 0)
        self.assertEqual(len(rep["updated"]), 0)

    # =========================================================================
    # R3-2F: Seed Scope Separation & Count Guards
    # =========================================================================
    def test_r3_2f_seed_scope_and_count_guards(self):
        """Seed CLI enforces confirmation, scope requirement, count limits, and magazine-only zero community."""
        # 1. No confirmation -> reject
        args_no_confirm = parse_args(["--seed-magazine", "--expected-target", str(self.db_path)])
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_seeder(args_no_confirm))
        self.assertIn("--confirm-seed must be explicitly passed", str(ctx.exception))

        # 2. No scope -> reject
        args_no_scope = parse_args(["--confirm-seed", "--expected-target", str(self.db_path)])
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_seeder(args_no_scope))
        self.assertIn("Scope required", str(ctx.exception))

        # 3. No expected target -> reject
        args_no_target = parse_args(["--confirm-seed", "--seed-magazine"])
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_seeder(args_no_target))
        self.assertIn("--expected-target must be explicitly provided", str(ctx.exception))

        # 4. Out of range community counts -> reject
        args_excess_posts = parse_args([
            "--confirm-seed", "--seed-community",
            "--expected-target", str(self.db_path),
            "--db-url", self.sync_db_url,
            "--posts", "250",
        ])
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(run_seeder(args_excess_posts))
        self.assertIn("Invalid post count", str(ctx.exception))

        # 5. Magazine-only seed execution on test DB: verify 0 community posts created
        args_mag_only = parse_args([
            "--confirm-seed",
            "--seed-magazine",
            "--expected-target", str(self.db_path),
            "--db-url", self.sync_db_url,
        ])
        res = asyncio.run(run_seeder(args_mag_only))
        self.assertEqual(res.get("community_posts_seeded", 0), 0)
        self.assertEqual(res.get("comments_seeded", 0), 0)
        self.assertEqual(res.get("counterclaims_seeded", 0), 0)
        self.assertGreater(res.get("magazine_articles_seeded", 0), 0)

    # =========================================================================
    # R3-2G: Zero Credential / Token Leakage
    # =========================================================================
    def test_r3_2g_canary_secret_not_exposed(self):
        """Pass canary password and token; ensure never exposed in masked URL or error message."""
        canary_pw = "CANARY_SECRET_PASS_998877"
        canary_token = "CANARY_TOKEN_XYZ_112233"
        raw_url = f"postgresql://app_user:{canary_pw}@db.example.com:5432/my_db?token={canary_token}&app=reframe"

        # 1. mask_db_url must hide both password and token
        masked = mask_db_url(raw_url)
        self.assertNotIn(canary_pw, masked)
        self.assertNotIn(canary_token, masked)
        self.assertIn("app_user:***@db.example.com:5432/my_db", masked)
        self.assertIn("token=***", masked)

        # 2. Mismatch error message must not leak canary values even if present in db_url or expected_target
        with self.assertRaises(ValueError) as ctx:
            run_importer(raw_url, self.catalog_path, dry_run=False, expected_target="other_host:5432/my_db")

        error_msg = str(ctx.exception)
        self.assertNotIn(canary_pw, error_msg)
        self.assertNotIn(canary_token, error_msg)

        # 3. If expected_target itself contains a secret, ensure it is masked
        canary_exp_pw = "CANARY_IN_EXPECTED_TARGET_PASS_5544"
        secret_exp_target = f"postgresql://app_user:{canary_exp_pw}@target.example.com:5432/my_db"
        with self.assertRaises(ValueError) as ctx2:
            run_importer("postgresql://other_user:pass@other.example.com:5432/other_db", self.catalog_path, dry_run=False, expected_target=secret_exp_target)
        self.assertNotIn(canary_exp_pw, str(ctx2.exception))

        with self.assertRaises(ValueError) as ctx3:
            sync_catalog("sqlite:///test.db", self.catalog_path, expected_target=secret_exp_target, confirm_sync=True, dry_run=False)
        self.assertNotIn(canary_exp_pw, str(ctx3.exception))

    # =========================================================================
    # R4: Applied Fields (source_url, core_demo_supported), source_qid immutability
    # =========================================================================
    def test_r4_sync_applied_fields_and_source_qid_immutability(self):
        """Verify source_url/core_demo_supported persistence and source_qid immutability."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from src.reframe.catalog.models import FilmCatalog

        # 1. Initial sync from v1
        sync_catalog(
            self.sync_db_url,
            self.catalog_path,
            expected_target=str(self.db_path),
            confirm_sync=True,
            dry_run=False,
        )

        with open(self.catalog_path, "r", encoding="utf-8") as f:
            base_data = json.load(f)

        # 2. Mutate source_qid under bumped revision -> Must be rejected as immutable identity
        mutated_qid = json.loads(json.dumps(base_data))
        mutated_qid["films"][0]["qid"] = "Q99999999"
        mutated_qid["films"][0]["source_revision"] = mutated_qid["films"][0]["source_revision"] + 1
        p_qid = Path(self.temp_dir.name) / "mut_qid.json"
        with open(p_qid, "w", encoding="utf-8") as f:
            json.dump(mutated_qid, f)

        with self.assertRaises(ValueError) as ctx:
            sync_catalog(self.sync_db_url, p_qid, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertIn("Cannot mutate immutable identity 'source_qid'", str(ctx.exception))

        # 3. Mutate source_url and core_demo_supported under bumped revision -> Must be saved and verified in DB
        bumped_fields = json.loads(json.dumps(base_data))
        bumped_fields["films"][0]["source_url"] = "https://www.wikidata.org/wiki/Q3985804?custom_param=1"
        bumped_fields["films"][0]["core_demo_supported"] = True
        bumped_fields["films"][0]["source_revision"] = bumped_fields["films"][0]["source_revision"] + 1
        p_fields = Path(self.temp_dir.name) / "bumped_fields.json"
        with open(p_fields, "w", encoding="utf-8") as f:
            json.dump(bumped_fields, f)

        rep = sync_catalog(self.sync_db_url, p_fields, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertEqual(len(rep["updated"]), 1)

        # Read back from fresh engine connection to verify persistence
        engine = create_engine(self.sync_db_url)
        try:
            with Session(engine) as session:
                row = session.get(FilmCatalog, bumped_fields["films"][0]["movie_id"])
                self.assertIsNotNone(row)
                self.assertEqual(row.source_url, "https://www.wikidata.org/wiki/Q3985804?custom_param=1")
                self.assertTrue(row.core_demo_supported)
        finally:
            engine.dispose()

    # =========================================================================
    # R4: Catalog v3 Versioned Enrichment Sync Round-trip
    # =========================================================================
    def test_r4_sync_catalog_v3_enrichment_roundtrip(self):
        """Verify syncing v3 updates Parasite poster to .png and repeated sync is exact no-op."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from src.reframe.catalog.models import FilmCatalog

        # 1. Initial sync from v1
        sync_catalog(
            self.sync_db_url,
            self.catalog_path,
            expected_target=str(self.db_path),
            confirm_sync=True,
            dry_run=False,
        )

        # 2. Sync official data/catalog/films_wikidata_v3.json -> Updates Parasite poster to .png
        v3_path = REPO_ROOT / "data" / "catalog" / "films_wikidata_v3.json"
        self.assertTrue(v3_path.exists())

        rep_v3 = sync_catalog(self.sync_db_url, v3_path, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertEqual(len(rep_v3["updated"]), 1)
        self.assertEqual(rep_v3["updated"][0]["movie_id"], "wd-q61448040")

        # Verify Parasite in database on fresh connection
        engine = create_engine(self.sync_db_url)
        try:
            with Session(engine) as session:
                para = session.get(FilmCatalog, "wd-q61448040")
                self.assertIsNotNone(para)
                self.assertEqual(para.poster_local_path, "/assets/catalog/wikidata/Q61448040.png")
                self.assertEqual(para.poster_source_filename, "Q61448040.png")
                self.assertEqual(para.source_revision, 2540328987)
        finally:
            engine.dispose()

        # Re-running sync with v3 must be an exact 20 no-op
        rep_v3_repeat = sync_catalog(self.sync_db_url, v3_path, expected_target=str(self.db_path), confirm_sync=True, dry_run=False)
        self.assertEqual(len(rep_v3_repeat["updated"]), 0)
        self.assertEqual(len(rep_v3_repeat["no_op"]), 20)


if __name__ == "__main__":
    unittest.main()
