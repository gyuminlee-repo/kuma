"""Planner contracts using real temporary Git repositories, no product imports.

Run with unittest for a quick tooling check; pytest's normal full suite collects
these cases too. These tests never stand in for product or real-data validation.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / ".." / "scripts" / "plan_incremental_audit.py"
spec = importlib.util.spec_from_file_location("incremental_audit_planner", SCRIPT.resolve())
assert spec is not None and spec.loader is not None
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class AuditPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kuma-audit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Audit test")
        self.git("config", "user.email", "audit@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("kuma_core/core.py", "def tested(): return 1\n")
        self.write("kuma_core/shared/helper.py", "SETTING = 1\n")
        self.write("src/caller.ts", "export const caller = 1;\n")
        self.write("bridge.py", "value = 1\n")
        self.write("tests/test_core.py", "def test_contract(): assert True\n")
        self.write("pyproject.toml", "[project]\nname='fixture'\n")
        self.groups = [
            {"id": "outer", "files": ["src/caller.ts", "bridge.py"]},
            {"id": "inner", "files": ["bridge.py", "kuma_core/core.py"]},
        ]
        self.write(planner.GROUPS, json.dumps({"groups": self.groups}))
        self.baseline = self.commit("baseline")
        self.registry = {
            "schema_version": 1, "comparison_base": self.baseline,
            "global_inputs": ["pyproject.toml", planner.GROUPS],
            "records": [{
                "id": "guard", "scope": "A deliberately narrow fixture guard",
                "reviewed_commit": self.baseline,
                "files": ["kuma_core/core.py"], "tests": ["tests/test_core.py"],
                "watch": ["kuma_core/shared/*"],
                "evidence": {"kind": "regression", "tested_commit": self.baseline,
                             "pull_request": "fixture PR", "ci_run": "fixture run"},
                "limitations": "Not a biological benchmark",
            }],
            "unverified": [{"id": "real-data", "reason": "Independent data not available"}],
        }
        self.write(planner.REGISTRY, json.dumps(self.registry))
        self.commit("record scoped evidence")

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], check=True,
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        return result.stdout.strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def report(self, **kwargs):
        repo = planner.Repository(self.root, committed_only=kwargs.pop("committed_only", False))
        return planner.plan(repo, self.registry, self.groups, **kwargs)

    def status(self, **kwargs):
        return self.report(**kwargs)["records"][0]["status"]

    def test_unchanged_scope_is_candidate_never_a_test_pass(self):
        report = self.report()
        self.assertEqual(report["records"][0]["status"], "reuse_candidate")
        self.assertTrue(report["full_ci_required"])
        self.assertFalse(report["automatic_test_skipping"])
        fingerprint = report["records"][0]["fingerprints"]["kuma_core/core.py"]
        self.assertEqual(fingerprint["reviewed"], fingerprint["head"])

    def test_unrelated_document_does_not_force_rereading_guard(self):
        self.write("docs/explanation.md", "New explanation\n")
        self.commit("docs")
        self.assertEqual(self.status(), "reuse_candidate")
        self.assertIn("docs/explanation.md", self.report()["unrecorded_changes"])

    def test_changed_implementation_requires_review(self):
        self.write("kuma_core/core.py", "def tested(): return 2\n")
        self.commit("change")
        self.assertEqual(self.status(), "review_required")

    def test_unchanged_source_but_changed_dependency_requires_review(self):
        self.write("kuma_core/shared/helper.py", "SETTING = 2\n")
        self.commit("dependency")
        self.assertEqual(self.status(), "review_required")

    def test_transitive_group_dependency_reaches_unchanged_source(self):
        self.write("src/caller.ts", "export const caller = 2;\n")
        self.commit("caller")
        row = self.report()["records"][0]
        self.assertEqual(row["status"], "review_required")
        self.assertEqual(row["dependency_groups"], ["inner", "outer"])
        self.assertIn("kuma_core/core.py", row["trigger_paths"])

    def test_global_environment_change_invalidates_context(self):
        self.write("pyproject.toml", "[project]\nname='changed'\n")
        self.commit("environment")
        self.assertEqual(self.status(), "review_required")

    def test_modified_regression_test_does_not_inherit_pass(self):
        self.write("tests/test_core.py", "def test_contract(): pass\n")
        self.commit("weaken test")
        self.assertEqual(self.status(), "review_required")

    def test_removed_test_is_unverified(self):
        (self.root / "tests/test_core.py").unlink()
        self.commit("remove regression")
        self.assertEqual(self.status(), "unverified")

    def test_unstaged_deleted_test_is_unverified(self):
        (self.root / "tests/test_core.py").unlink()
        self.assertEqual(self.status(), "unverified")

    def test_staged_and_unstaged_changes_are_both_included(self):
        self.write("kuma_core/core.py", "def tested(): return 3\n")
        self.git("add", "kuma_core/core.py")
        self.write("kuma_core/shared/helper.py", "SETTING = 4\n")
        report = self.report()
        self.assertIn("kuma_core/core.py", report["working_tree_changes"])
        self.assertIn("kuma_core/shared/helper.py", report["working_tree_changes"])
        self.assertEqual(report["records"][0]["status"], "review_required")

    def test_untracked_new_dependency_is_not_invisible(self):
        self.write("kuma_core/shared/new.py", "value = 1\n")
        self.assertEqual(self.status(), "review_required")

    def test_unmapped_new_code_requires_manual_impact_review(self):
        self.write("new_plugin/run.py", "value = 1\n")
        report = self.report()
        self.assertIn("new_plugin/run.py", report["unrecorded_changes"])
        self.assertTrue(report["manual_impact_review_required"])

    def test_rename_and_delete_do_not_look_unchanged(self):
        self.git("mv", "kuma_core/core.py", "kuma_core/renamed.py")
        self.commit("rename")
        report = self.report()
        self.assertIn("kuma_core/core.py", report["changed_files"])
        self.assertIn("kuma_core/renamed.py", report["changed_files"])
        self.assertEqual(report["records"][0]["status"], "review_required")

    def test_spaces_and_unicode_in_paths_survive_git_inventory(self):
        name = "kuma_core/shared/a space 한글.py"
        self.write(name, "value = 1\n")
        self.commit("path")
        self.assertIn(name, self.report()["changed_files"])
        self.assertEqual(self.status(), "review_required")

    def test_committed_only_ignores_dirty_code(self):
        self.write("kuma_core/core.py", "def tested(): return 9\n")
        self.assertEqual(self.status(), "review_required")
        self.assertEqual(self.status(committed_only=True), "reuse_candidate")

    def test_missing_old_commit_fails_closed(self):
        self.registry["records"][0]["reviewed_commit"] = "f" * 40
        report = self.report()
        self.assertFalse(report["plan_complete"])
        self.assertEqual(report["records"][0]["status"], "review_required")

    def test_nonancestor_commit_cannot_certify_current_branch(self):
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "--orphan", "unrelated")
        self.write("other.txt", "unrelated\n")
        unrelated = self.commit("unrelated root")
        self.git("checkout", "--detach", head)
        self.registry["records"][0]["reviewed_commit"] = unrelated
        self.assertFalse(self.report()["plan_complete"])

    def test_summary_base_override_cannot_reset_a_record_baseline(self):
        self.write("kuma_core/core.py", "def tested(): return 7\n")
        head = self.commit("change")
        report = self.report(base=head)
        self.assertEqual(report["changed_files"], [])
        self.assertEqual(report["records"][0]["status"], "review_required")

    def test_fabricated_file_at_old_baseline_is_not_reusable(self):
        self.registry["records"][0]["files"].append("never-reviewed.py")
        self.assertFalse(self.report()["plan_complete"])

    def test_external_evidence_stays_unverified_even_when_code_unchanged(self):
        report = self.report()
        self.assertEqual(report["unverified_work"][0]["status"], "unverified")

    def test_duplicate_or_empty_records_rejected(self):
        for records in ([], self.registry["records"] * 2):
            with self.subTest(records=len(records)):
                value = deepcopy(self.registry)
                value["records"] = records
                with self.assertRaises(ValueError):
                    planner.validate_registry(value)

    def test_mutable_revision_and_unsafe_paths_rejected(self):
        for field, value in (("reviewed_commit", "main"), ("files", ["../outside"]),
                             ("tests", ["tests/*.py"]), ("watch", ["/tmp/data"])):
            with self.subTest(field=field):
                registry = deepcopy(self.registry)
                registry["records"][0][field] = value
                with self.assertRaises(ValueError):
                    planner.validate_registry(registry)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            planner.read_json(b'{"records": [], "records": [1]}')

    def test_unknown_schema_and_invalid_dependency_map_rejected(self):
        for version in (True, 2, "1"):
            value = deepcopy(self.registry)
            value["schema_version"] = version
            with self.assertRaises(ValueError):
                planner.validate_registry(value)
        with self.assertRaises(ValueError):
            planner.validate_groups({})

    def test_globs_cover_zero_directories_and_brace_alternatives(self):
        self.assertTrue(planner.matches("src/caller.ts", ["src/**/*.{ts,tsx}"]))
        self.assertTrue(planner.matches("src/deep/caller.tsx", ["src/**/*.{ts,tsx}"]))
        self.assertFalse(planner.matches("src/caller.py", ["src/**/*.{ts,tsx}"]))
        self.assertFalse(planner.matches("SRC/caller.ts", ["src/*"]))

    def test_cyclic_groups_terminate(self):
        groups = [{"id": "a", "files": ["a", "b"]}, {"id": "b", "files": ["b", "a"]}]
        impacted, triggered = planner.impact_closure({"a"}, {"a", "b"}, groups)
        self.assertEqual(impacted, {"a", "b"})
        self.assertEqual(triggered, ["a", "b"])

    def test_cli_writes_plan_without_running_tests_or_mutating_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            before = (self.root / planner.REGISTRY).read_bytes()
            self.assertEqual(planner.main(["--repo-root", str(self.root), "--json", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["head_commit"], self.git("rev-parse", "HEAD"))
            self.assertEqual((self.root / planner.REGISTRY).read_bytes(), before)
            self.assertFalse(report["automatic_test_skipping"])

    def test_committed_only_reads_committed_registry_not_a_dirty_replacement(self):
        self.write(planner.REGISTRY, "not json")
        self.assertEqual(planner.main(["--repo-root", str(self.root), "--committed-only"]), 0)
        self.assertEqual(planner.main(["--repo-root", str(self.root)]), 1)

    def test_missing_comparison_base_is_an_error_not_zero_changes(self):
        self.assertEqual(planner.main(["--repo-root", str(self.root), "--base", "e" * 40]), 1)

    def test_report_cannot_overwrite_tracked_source(self):
        source = self.root / "kuma_core/core.py"
        before = source.read_bytes()
        self.assertEqual(planner.main(["--repo-root", str(self.root), "--json", str(source)]), 1)
        self.assertEqual(source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
