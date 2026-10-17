"""Keep the main-push label check independent of package-manager setup."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def job_block(workflow: str, job: str) -> str:
    """Read one top-level job from this repository's block-style CI YAML."""
    match = re.search(
        rf"^  {re.escape(job)}:\n(.*?)(?=^  [\w-]+:\n|\Z)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"CI job not found: {job}")
    return match.group(1)


class MainLabelSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.main_label = job_block(self.workflow, "main-label")

    def test_node_only_job_disables_automatic_package_manager_cache(self) -> None:
        # setup-node v5 reads package.json's packageManager even with no cache
        # input. Without this opt-out it calls an absent pnpm before the check.
        setup_steps = [
            step for step in re.split(r"(?m)^      - ", self.main_label)
            if step.startswith("uses: actions/setup-node@")
        ]
        self.assertEqual(len(setup_steps), 1)
        self.assertRegex(setup_steps[0], r"(?m)^          package-manager-cache: false$")
        self.assertNotRegex(setup_steps[0], r"(?m)^          cache:")
        self.assertNotIn("pnpm/action-setup@", self.main_label)
        self.assertEqual(
            re.findall(r"(?m)^        run: (.+)$", self.main_label),
            ["node scripts/check-version-label.mjs"],
        )

    def test_main_push_scope_and_label_history_are_preserved(self) -> None:
        self.assertIn(
            "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n",
            self.main_label,
        )
        self.assertRegex(self.main_label, r"(?m)^          fetch-depth: 50$")

    def test_dependency_jobs_still_install_pnpm_before_enabling_its_cache(self) -> None:
        for job in ("frontend-typecheck", "rust-check"):
            with self.subTest(job=job):
                block = job_block(self.workflow, job)
                self.assertLess(
                    block.index("uses: pnpm/action-setup@"),
                    block.index("uses: actions/setup-node@"),
                )
                self.assertRegex(block, r"(?m)^          cache: pnpm$")


if __name__ == "__main__":
    unittest.main()
