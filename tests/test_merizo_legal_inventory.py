"""Legal collection unit checks; no upstream model or inference required."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merizo_legal_inventory", ROOT / "scripts/merizo_windows_smoke/collect_legal_inventory.py")
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


class LegalInventoryTests(unittest.TestCase):
    def test_missing_legal_text_is_explicit_and_pins_are_checked_first(self):
        dist = SimpleNamespace(metadata={"Name": "fixture-dep", "License": "unknown"}, version="1")
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source / "LICENSE").write_text("test upstream legal text")
                events = []
                verifier = Mock(side_effect=lambda _: events.append("pins") or {"test": "hash"})
                collector = SimpleNamespace(
                    dependency_closure=lambda _: events.append("closure") or [(dist, ["runtime"])],
                    legal_files=Mock(side_effect=ValueError("missing grant") if missing else None,
                                     return_value=[{"text": "fixture legal text", "sha256": "a" * 64}]))
                spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None))
                with patch.object(inventory.importlib.util, "spec_from_file_location", return_value=spec), \
                     patch.object(inventory.importlib.util, "module_from_spec", return_value=collector), \
                     patch.dict(sys.modules, {"run": SimpleNamespace(COMMIT="pinned", verify_upstream=verifier)}), \
                     patch.object(inventory.sys, "base_prefix", str(source)):
                    report = inventory.collect(source)
                self.assertEqual(events, ["pins", "closure"])
                self.assertFalse(report["distribution_cleared"])
                self.assertFalse(report["truncated"])
                self.assertEqual(report["collection_status"], "incomplete" if missing else "package_texts_collected")
                self.assertEqual(bool(report["missing_evidence"]), missing)
                self.assertEqual(report["distributions"][0]["legal_files"] == [], missing)

    def test_requirements_are_explicit_and_separate(self):
        here = ROOT / "scripts/merizo_windows_smoke"
        runtime = inventory.requirements(here / "requirements.txt")
        packaging = inventory.requirements(here / "freezer-requirements.txt")
        self.assertIn("numpy==1.24.3", runtime)
        self.assertIn("pyinstaller==6.16.0", packaging)
        self.assertFalse(any("primer3" in item for item in runtime + packaging))

    def test_empty_or_option_requirements_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.txt"
            for value in ("", "numpy>=1", "--index-url=https://example.invalid"):
                path.write_text(value)
                with self.assertRaises(ValueError):
                    inventory.requirements(path)

    def test_original_text_is_bounded_hashed_and_not_a_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LICENSE"
            path.write_bytes(b"test legal text\n")
            result = inventory.original_text(path, "fixture/LICENSE")
            self.assertEqual(result["text"], "test legal text\n")
            self.assertEqual(result["path"], "fixture/LICENSE")
            self.assertEqual(len(result["sha256"]), 64)
            with patch.object(inventory, "MAX_LEGAL_BYTES", 4):
                with self.assertRaises(ValueError):
                    inventory.original_text(path, "fixture/LICENSE")
            path.write_bytes(b"\xff\x00")
            with self.assertRaises(UnicodeError):
                inventory.original_text(path, "fixture/LICENSE")

    def test_workflow_collects_before_source_removal_and_uploads_text_only(self):
        for name in ("merizo-platform-smoke.yml", "merizo-windows-smoke.yml"):
            text = (ROOT / ".github/workflows" / name).read_text()
            self.assertLess(text.index("collect_legal_inventory.py --source"), text.index("Remove original"))
            self.assertIn("merizo-smoke-results/legal-inventory.json", text)
            artifact = text.split("uses: actions/upload-artifact@v4", 1)[1].split("      - name:", 1)[0]
            self.assertNotIn(".pt", artifact)
            self.assertNotIn("dist/", artifact)


if __name__ == "__main__":
    unittest.main()
