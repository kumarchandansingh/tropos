"""Synthetic regression cases for destructive-operation boundaries."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from katharo.actions import Actions
from katharo.documents import extract, normalize, similarity
from katharo.domain import ReviewError, validate_selection
from katharo.filesystem import hash_file, validate_root
from katharo.scanner import scan
from katharo.store import Store


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "Downloads"
        self.root.mkdir()
        self.quarantine = self.base / "Quarantine"
        self.store = Store(self.base / "state" / "inventory.sqlite")
        self.actions = Actions(self.store)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def fixture(self):
        (self.root / "resume.txt").write_text("Synthetic resume only.", encoding="utf-8")
        (self.root / "different-name.txt").write_text("Synthetic resume only.", encoding="utf-8")
        (self.root / "unique.txt").write_text("A completely different file.", encoding="utf-8")
        return self.scan()

    def scan(self, documents=False):
        return scan(str(self.root), True, documents, lambda *_: None, lambda: False, [])

    def plan(self, result):
        group = next(g for g in result["groups"] if g["kind"] == "exact")
        return self.actions.prepare(result, [group["files"][1]["id"]], str(self.quarantine))

    def test_different_names_exact_match(self):
        result = self.fixture()
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["kind"], "exact")
        self.assertEqual(result["recoverable"], len(b"Synthetic resume only."))

    def test_office_owner_records_excluded(self):
        (self.root / "~$one.docx").write_bytes(b"owner")
        (self.root / "~$two.xlsx").write_bytes(b"owner")
        result = self.scan(documents=True)
        self.assertEqual(result["office_records_skipped"], 2)
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["file_count"], 0)

    def test_mixed_formats_require_individual_review(self):
        (self.root / "one.txt").write_bytes(b"same bytes")
        (self.root / "two.pdf").write_bytes(b"same bytes")
        result = self.scan()
        self.assertFalse(result["groups"][0]["batch_eligible"])
        self.assertEqual(result["groups"][0]["kind"], "exact")

    def test_same_size_different_bytes_not_duplicate(self):
        (self.root / "one.bin").write_bytes(b"abc")
        (self.root / "one (1).bin").write_bytes(b"xyz")
        self.assertEqual(self.scan()["groups"], [])

    def test_keep_one_enforced(self):
        result = self.fixture()
        with self.assertRaises(ReviewError):
            validate_selection(result["groups"], {f["id"] for f in result["groups"][0]["files"]})

    def test_unknown_selection_rejected(self):
        with self.assertRaises(ReviewError):
            validate_selection(self.fixture()["groups"], {"invented-id"})

    def test_document_matches_not_actionable(self):
        with self.assertRaises(ReviewError):
            validate_selection([{"kind": "content", "files": [{"id": "x"}, {"id": "y"}]}], {"x"})

    def test_unwritable_destination_rejected_before_approval(self):
        result = self.fixture()
        with patch("katharo.actions.tempfile.TemporaryDirectory", side_effect=PermissionError):
            with self.assertRaisesRegex(ReviewError, "No files were moved"):
                self.plan(result)
        self.assertEqual(self.store.list("plan"), [])
        self.assertTrue(all(Path(f["path"]).exists() for f in result["files"]))

    def test_initial_manifest_failure_moves_nothing(self):
        result = self.fixture()
        plan = self.plan(result)
        with patch.object(self.actions, "journal", side_effect=PermissionError):
            with self.assertRaisesRegex(ReviewError, "No files were moved"):
                self.actions.execute(plan["id"])
        self.assertEqual(self.store.get("plan", plan["id"])["status"], "blocked")
        self.assertTrue(all(Path(f["path"]).exists() for f in result["files"]))

    def test_same_drive_quarantine_and_restore(self):
        plan = self.plan(self.fixture())
        original = Path(plan["items"][0]["file"]["path"])
        moved = self.actions.execute(plan["id"])
        self.assertEqual(moved["status"], "completed")
        self.assertFalse(original.exists())
        self.assertTrue(Path(moved["items"][0]["quarantine_path"]).exists())
        self.assertTrue((self.quarantine / plan["id"] / "manifest.json").exists())
        restored = self.actions.restore(plan["id"])
        self.assertEqual(restored["status"], "restored")
        self.assertEqual(original.read_text(), "Synthetic resume only.")

    def test_changed_extra_never_moved(self):
        plan = self.plan(self.fixture())
        original = Path(plan["items"][0]["file"]["path"])
        original.write_text("Modified after review")
        outcome = self.actions.execute(plan["id"])
        self.assertEqual(outcome["items"][0]["status"], "failed")
        self.assertTrue(original.exists())

    def test_changed_keeper_never_moves_extra(self):
        plan = self.plan(self.fixture())
        Path(plan["items"][0]["keeper"]["path"]).write_text("Changed keeper")
        outcome = self.actions.execute(plan["id"])
        self.assertEqual(outcome["items"][0]["status"], "failed")
        self.assertTrue(Path(plan["items"][0]["file"]["path"]).exists())

    def test_restore_refuses_overwrite(self):
        plan = self.plan(self.fixture())
        moved = self.actions.execute(plan["id"])
        original = Path(plan["items"][0]["file"]["path"])
        original.write_text("New valuable file")
        outcome = self.actions.restore(plan["id"])
        self.assertEqual(original.read_text(), "New valuable file")
        self.assertIn("occupied", outcome["items"][0]["error"])
        self.assertTrue(Path(moved["items"][0]["quarantine_path"]).exists())

    def test_plan_cannot_execute_twice(self):
        plan = self.plan(self.fixture())
        self.actions.execute(plan["id"])
        with self.assertRaises(ReviewError):
            self.actions.execute(plan["id"])

    def test_interrupted_move_can_restore_available_quarantine(self):
        plan = self.plan(self.fixture())
        moved = self.actions.execute(plan["id"])
        moved["status"] = "executing"
        moved["items"][0]["status"] = "moving"
        self.store.save("plan", moved)
        restored = self.actions.restore(plan["id"])
        self.assertEqual(restored["status"], "restored")
        self.assertTrue(Path(plan["items"][0]["file"]["path"]).exists())

    def test_changed_quarantine_refuses_restore(self):
        plan = self.plan(self.fixture())
        moved = self.actions.execute(plan["id"])
        quarantined = Path(moved["items"][0]["quarantine_path"])
        quarantined.write_text("Modified quarantined content")
        result = self.actions.restore(plan["id"])
        self.assertIn("changed", result["items"][0]["error"])
        self.assertFalse(Path(plan["items"][0]["file"]["path"]).exists())

    def test_empty_pdf_extraction_is_unknown(self):
        from pypdf import PdfWriter

        target = self.root / "blank.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with target.open("wb") as stream:
            writer.write(stream)
        self.assertEqual(extract(target).status, "unknown")

    def test_docx_extracts_text_without_ai(self):
        from zipfile import ZipFile

        target = self.root / "example.docx"
        with ZipFile(target, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic document</w:t></w:r></w:p></w:body></w:document>',
            )
        result = extract(target)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.text, "Synthetic document")

    def test_quarantine_inside_scan_rejected(self):
        result = self.fixture()
        with self.assertRaises(ReviewError):
            self.actions.prepare(
                result, [result["groups"][0]["files"][1]["id"]], str(self.root / "quarantine")
            )

    def test_relative_destination_rejected(self):
        result = self.fixture()
        with self.assertRaises(ReviewError):
            self.actions.prepare(result, [result["groups"][0]["files"][1]["id"]], "relative-folder")

    def test_cancelled_scan_no_actionable_result(self):
        self.fixture()
        result = scan(str(self.root), True, False, lambda *_: None, lambda: True, [])
        self.assertEqual(result["status"], "cancelled")

    def test_hard_links_not_double_counted(self):
        (self.root / "first.bin").write_bytes(b"hardlink")
        try:
            os.link(self.root / "first.bin", self.root / "alias.bin")
        except OSError:
            self.skipTest("Hard links unavailable on this filesystem")
        result = self.scan()
        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["groups"], [])

    def test_link_root_rejected(self):
        try:
            (self.base / "alias").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ReviewError):
            validate_root(str(self.base / "alias"))

    def test_hash_change_during_read_rejected(self):
        target = self.root / "changing.bin"
        target.write_bytes(b"test")
        with patch("katharo.filesystem.signature", side_effect=[(1,), (1,), (2,), (1,)]):
            with self.assertRaises(ReviewError):
                hash_file(target)

    def test_document_normalization_and_revision(self):
        self.assertEqual(normalize("A\r\n  resume\t"), "A resume")
        self.assertEqual(
            similarity("one two three four five six", "one two three four five six"), 1
        )
        self.assertEqual(similarity("one two three four five", "six seven eight nine ten"), 0)

    def test_empty_text_unknown(self):
        target = self.root / "empty.txt"
        target.write_text("   ")
        self.assertEqual(extract(target).status, "unknown")

    def test_document_matching_different_raw_bytes(self):
        (self.root / "a.txt").write_text("One two three four five six.\n", encoding="utf-8")
        (self.root / "b.txt").write_text("One  two three four five six.", encoding="utf-8")
        result = self.scan(documents=True)
        self.assertTrue(any(g["kind"] == "content" for g in result["groups"]))
        self.assertFalse(any(g["kind"] == "exact" for g in result["groups"]))


if __name__ == "__main__":
    unittest.main()
