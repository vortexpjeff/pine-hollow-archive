import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_labels import audit_database, is_species_label, derive_tags
from schema_hardening import ensure_review_hardening_schema, training_eligibility_sql


class AuditLabelsTest(unittest.TestCase):
    def make_db(self, tmp_path):
        db = tmp_path / "archive.db"
        conn = sqlite3.connect(db)
        conn.execute("""
            CREATE TABLE clips (
                id INTEGER PRIMARY KEY,
                source TEXT,
                source_label TEXT,
                review_status TEXT,
                human_label TEXT,
                human_tags TEXT,
                perch_embedding BLOB,
                model_pred TEXT
            )
        """)
        return db, conn

    def make_hardened_db(self, tmp_path):
        db, conn = self.make_db(tmp_path)
        ensure_review_hardening_schema(conn)
        return db, conn

    def test_is_species_label_accepts_binomial_and_rejects_acoustic_classes(self):
        self.assertTrue(is_species_label("Dryophytes chrysoscelis"))
        self.assertTrue(is_species_label("Thryothorus_ludovicianus"))
        self.assertFalse(is_species_label("frog"))
        self.assertFalse(is_species_label("background"))

    def test_derive_tags_uses_tag_map_without_flattening_species(self):
        tag_map = {"Dryophytes chrysoscelis": "frog"}
        self.assertEqual(
            derive_tags(["Dryophytes chrysoscelis"], tag_map),
            ["Dryophytes chrysoscelis", "frog"],
        )

    def test_audit_blocks_invalid_human_tags_json(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_db(Path(td))
            conn.execute("INSERT INTO clips VALUES (1, 'insectnet', 'frog', 'confirmed', 'frog', 'not-json', X'00', NULL)")
            conn.commit(); conn.close()

            result = audit_database(db, tag_map_path=None)

            self.assertEqual(result.block_count, 1)
            self.assertTrue(any("invalid human_tags JSON" in issue.message for issue in result.issues))

    def test_audit_blocks_background_mixed_with_target_taxa(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_db(Path(td))
            conn.execute(
                "INSERT INTO clips VALUES (1, 'insectnet', 'frog', 'confirmed', 'background, frog', ?, X'00', NULL)",
                (json.dumps(["background", "frog"]),),
            )
            conn.commit(); conn.close()

            result = audit_database(db, tag_map_path=None)

            self.assertEqual(result.block_count, 1)
            self.assertTrue(any("background mixed with target labels" in issue.message for issue in result.issues))

    def test_audit_warns_model_prediction_as_human_label(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_db(Path(td))
            conn.execute(
                "INSERT INTO clips VALUES (1, 'insectnet', 'frog', 'confirmed', 'frog', ?, X'00', 'frog')",
                (json.dumps(["frog"]),),
            )
            conn.commit(); conn.close()

            result = audit_database(db, tag_map_path=None)

            self.assertEqual(result.block_count, 0)
            self.assertEqual(result.warn_count, 1)
            self.assertTrue(any("human label exactly mirrors model_pred" in issue.message for issue in result.issues))

    def test_audit_warns_species_without_derived_class(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            db, conn = self.make_db(tmp_path)
            conn.execute(
                "INSERT INTO clips VALUES (1, 'insectnet', 'Dryophytes chrysoscelis', 'confirmed', 'Dryophytes chrysoscelis', ?, X'00', NULL)",
                (json.dumps(["Dryophytes chrysoscelis"]),),
            )
            conn.commit(); conn.close()
            tag_map = tmp_path / "tag_map.json"
            tag_map.write_text(json.dumps({"tags": {"frog": {"perch_labels": ["Dryophytes chrysoscelis"]}}}))

            result = audit_database(db, tag_map_path=tag_map)

            self.assertEqual(result.block_count, 0)
            self.assertEqual(result.warn_count, 1)
            self.assertTrue(any("missing derived class tag" in issue.message for issue in result.issues))


    def test_schema_migration_backfills_legacy_training_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_db(Path(td))
            conn.execute(
                "INSERT INTO clips VALUES (1, 'public', 'frog', 'confirmed', 'frog', ?, X'00', NULL)",
                (json.dumps(["frog"]),),
            )
            ensure_review_hardening_schema(conn)

            row = conn.execute("SELECT label_certainty, review_source FROM clips WHERE id=1").fetchone()
            conn.close()

            self.assertEqual(row, ("probable", "public_dataset"))

    def test_training_gate_excludes_needs_second_pass_and_batch_auto(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_hardened_db(Path(td))
            rows = [
                (1, "insectnet", "frog", "confirmed", "frog", json.dumps(["frog"]), b"0", None, "probable", "human_review"),
                (2, "insectnet", "frog", "needs_second_pass", "frog", json.dumps(["frog"]), b"0", None, "possible", "human_review"),
                (3, "insectnet", "frog", "confirmed", "frog", json.dumps(["frog"]), b"0", None, "probable", "batch_auto_accept"),
                (4, "insectnet", "frog", "confirmed", "frog", json.dumps(["frog"]), b"0", None, "unsure", "human_review"),
            ]
            conn.executemany(
                "INSERT INTO clips (id, source, source_label, review_status, human_label, human_tags, perch_embedding, model_pred, label_certainty, review_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            ids = [r[0] for r in conn.execute(f"SELECT id FROM clips WHERE {training_eligibility_sql()} ORDER BY id")]
            conn.close()

            self.assertEqual(ids, [1])

    def test_audit_blocks_confirmed_batch_auto_label(self):
        with tempfile.TemporaryDirectory() as td:
            db, conn = self.make_hardened_db(Path(td))
            conn.execute(
                "INSERT INTO clips (id, source, source_label, review_status, human_label, human_tags, perch_embedding, model_pred, label_certainty, review_source) VALUES (1, 'insectnet', 'frog', 'confirmed', 'frog', ?, X'00', NULL, 'probable', 'batch_auto_accept')",
                (json.dumps(["frog"]),),
            )
            conn.commit(); conn.close()

            result = audit_database(db, tag_map_path=None)

            self.assertGreaterEqual(result.block_count, 1)
            self.assertTrue(any("batch auto label" in issue.message for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
