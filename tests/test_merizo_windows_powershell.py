"""Launcher contract checks; no frozen executable, Torch or model is run.

Text checks guard the intended Windows-only safety contract, not its native
behavior. If PowerShell is installed, also parse the complete script and compile
its embedded C# helper without invoking the launcher or the Windows APIs.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/merizo_windows_smoke"
SCRIPT = HARNESS / "run_frozen.ps1"
SOURCE = SCRIPT.read_text(encoding="utf-8")


class FrozenPowerShellContracts(unittest.TestCase):
    def test_explicit_interface_and_small_report_name(self):
        header = SOURCE.split("Set-StrictMode", 1)[0]
        names = re.findall(r"\[Parameter\(Mandatory\)\]\[string\]\s+\$(\w+)", header)
        self.assertEqual(names, ["PackageDirectory", "Fixture", "ResultDirectory", "PinReport"])
        self.assertIn("'frozen-windows-cpu.json'", SOURCE)
        self.assertIn("$maxReportBytes = 2MB", SOURCE)
        self.assertIn("Read-SmallJson $runtimeReport 1MB", SOURCE)

    def test_pins_match_shared_inference_constants(self):
        tree = ast.parse((HARNESS / "run.py").read_text(encoding="utf-8"))
        constants = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"COMMIT", "INPUT_SHA", "WEIGHTS"}
        }
        self.assertIn(f"$expectedCommit = '{constants['COMMIT']}'", SOURCE)
        self.assertIn(f"$expectedInput = '{constants['INPUT_SHA']}'", SOURCE)
        for name, digest in constants["WEIGHTS"].items():
            self.assertIn(f"'{name}' = '{digest}'", SOURCE)
        self.assertIn("$pins.verified_before_build -isnot [bool]", SOURCE)
        self.assertIn("Assert-WeightPins $pins.weights_sha256", SOURCE)
        self.assertIn("Assert-WeightPins $runtime.weights_sha256", SOURCE)
        self.assertIn("$runtime.frozen -isnot [bool]", SOURCE)

    def test_paths_resolved_disjoint_and_reparse_checked(self):
        for argument in ("PackageDirectory", "Fixture", "PinReport", "ResultDirectory"):
            self.assertIn(f"Get-SafeFullPath ${argument}", SOURCE)
        self.assertIn("[IO.File]::GetAttributes($cursor)", SOURCE)
        self.assertIn("[IO.Directory]::GetParent($cursor)", SOURCE)
        self.assertIn("[IO.FileAttributes]::ReparsePoint", SOURCE)
        self.assertIn("(Test-AtOrBelow $Left $Right) -or (Test-AtOrBelow $Right $Left)", SOURCE)
        self.assertIn("Assert-Disjoint $source $package", SOURCE)
        self.assertIn("Assert-Disjoint $runtimeDirectory $other", SOURCE)
        self.assertIn("@($repo, $package, $source, $resultDirectoryPath)", SOURCE)

    def test_source_absence_precedes_exe_and_only_owned_temp_is_deleted(self):
        launch = SOURCE.index("$process = [Diagnostics.Process]::Start($info)")
        self.assertLess(SOURCE.index("if (Test-Path -LiteralPath $source)"), launch)
        self.assertLess(SOURCE.index("Official source reappeared before launch."), launch)
        removals = re.findall(r"^\s*Remove-Item[^\r\n]+", SOURCE, re.MULTILINE)
        self.assertEqual([line.strip() for line in removals], [
            "Remove-Item -LiteralPath $runtimeDirectory -Recurse -Force"
        ])
        self.assertIn("if ($runtimeOwned)", SOURCE)
        self.assertIn("$report.runtime_directory_removed = -not (Test-Path", SOURCE)

    def test_explicit_frozen_launch_has_no_system_python_bootstrap(self):
        self.assertIn("'merizo-frozen-smoke.exe'", SOURCE)
        self.assertIn("$info.FileName = $exe", SOURCE)
        self.assertIn("$info.ArgumentList.Add($argument)", SOURCE)
        self.assertIn("@('--fixture', $runtimeFixture, '--output', $runtimeReport)", SOURCE)
        self.assertIn("$info.UseShellExecute = $false", SOURCE)
        self.assertNotIn("sys.executable", SOURCE)
        self.assertNotRegex(SOURCE, r"(?im)^\s*(?:&\s*)?(?:python(?:\.exe)?|py\.exe)\s")

    def test_environment_allowlist_and_isolation_evidence(self):
        self.assertIn("$info.Environment.Clear()", SOURCE)
        self.assertIn("$info.Environment['PATH'] = $systemDirectory + ';' + $systemRoot", SOURCE)
        self.assertNotIn("$env:PATH", SOURCE)
        self.assertNotRegex(SOURCE, r"Environment\['PYTHON(?:HOME|PATH)'\]\s*=")
        self.assertIn("'kuma merizo frozen '", SOURCE)
        self.assertIn("[IO.File]::Copy($fixturePath, $runtimeFixture, $false)", SOURCE)
        self.assertIn("system_python_physically_removed = $false", SOURCE)
        self.assertIn("inherited_environment_cleared = $true", SOURCE)

    def test_gate_job_watchdog_and_tree_death_verification(self):
        self.assertIn("$timeoutSeconds = 300", SOURCE)
        self.assertIn("JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE", SOURCE)
        self.assertIn("AssignProcessToJobObject", SOURCE)
        self.assertIn("TerminateJobObject", SOURCE)
        self.assertIn("QueryInformationJobObject", SOURCE)
        self.assertLess(SOURCE.index("$job.Assign($process)"), SOURCE.index("[IO.File]::WriteAllText($gate, 'ready')"))
        self.assertIn("Join-Path $systemDirectory 'taskkill.exe'", SOURCE)
        self.assertIn("@('/PID', [string] $Process.Id, '/T', '/F')", SOURCE)
        self.assertIn("$killer.WaitForExit(5000)", SOURCE)
        self.assertIn("$deathWatch.Elapsed.TotalSeconds -lt 10", SOURCE)
        self.assertIn("if ($rootExited -and $active -eq 0) { return $true }", SOURCE)
        self.assertIn("$report.process_tree_termination_verified = $false", SOURCE)
        self.assertIn("$report.status = 'cleanup_failed'", SOURCE)

    def test_metrics_and_output_are_bounded(self):
        self.assertIn("$process.WorkingSet64", SOURCE)
        self.assertIn("$process.PeakWorkingSet64", SOURCE)
        self.assertIn("$watch.Elapsed.TotalSeconds", SOURCE)
        self.assertIn("$report.package_bytes = $stats.package_bytes", SOURCE)
        self.assertIn("$report.package_file_count = $stats.package_file_count", SOURCE)
        self.assertIn("char[] buffer = new char[4096]", SOURCE)
        self.assertIn("combined.Substring(combined.Length - 2048)", SOURCE)
        self.assertIn("::Drain($process.StandardError, $true)", SOURCE)
        self.assertIn("if ($report.status -cne 'passed' -and $stderrTail.Length -gt 0)", SOURCE)
        self.assertNotIn(".ReadToEnd", SOURCE)
        self.assertIn("[Text.Encoding]::UTF8.GetByteCount($json) -gt $maxReportBytes", SOURCE)
        self.assertLess(SOURCE.index("$stdout = $null"), SOURCE.index("$watch.Start()"))
        self.assertLess(SOURCE.index("$stderr = $null"), SOURCE.index("$watch.Start()"))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell parser is not installed; native Windows CI required")
    def test_powershell_parses_and_embedded_job_helper_compiles(self):
        # Parse only; do not dot-source the script or start any packaged code.
        command = r"""
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:KUMA_FROZEN_PROBE_SCRIPT, [ref] $tokens, [ref] $errors)
if ($errors.Count -ne 0) { throw ($errors | Out-String) }
$text = [IO.File]::ReadAllText($env:KUMA_FROZEN_PROBE_SCRIPT)
$match = [regex]::Match($text, "(?ms)^\`$nativeHelpers = @'\r?\n(.*?)\r?\n'@")
if (-not $match.Success) { throw 'Embedded native helper missing.' }
Add-Type -TypeDefinition $match.Groups[1].Value
"""
        executable = shutil.which("pwsh")
        assert executable is not None
        result = subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
            env={**os.environ, "KUMA_FROZEN_PROBE_SCRIPT": str(SCRIPT)},
            cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
