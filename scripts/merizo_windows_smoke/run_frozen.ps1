#Requires -Version 7.0
<#
Test-only, native Windows frozen-runtime probe. The workflow removes the verified
upstream checkout before this script runs. Never remove a path from build JSON.
Only small combined JSON (with a bounded failure stderr tail) is retained;
no raw process logs or runtime are saved.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $PackageDirectory,
    [Parameter(Mandatory)][string] $Fixture,
    [Parameter(Mandatory)][string] $ResultDirectory,
    [Parameter(Mandatory)][string] $PinReport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$timeoutSeconds = 300
$maxReportBytes = 2MB
$expectedCommit = '41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd'
$expectedInput = 'd4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161'
$expectedWeights = @{
    'weights_part_0.pt' = '8b90ad1967c3e445aca7ed3d53135190ceaf8e100d68afd1543e5e8d28547151'
    'weights_part_1.pt' = '644f711b9573b44fc25a0bc0631ee9ab43f7fbd796db0a382298755057a2fa38'
    'weights_part_2.pt' = 'ddafe5fa5dfa729eb8715757004d2d3e4e9798f96ea43c689e799ef91af8c2b8'
}

function Get-SafeFullPath([string] $Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Empty filesystem path.' }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    # Local drive paths only: avoid UNC/device paths, alternate data streams and
    # aliases produced by trailing spaces/dots. Inspect every existing ancestor,
    # including dangling reparse points; missing source paths are permitted.
    if ($full -notmatch '^[A-Za-z]:\\' -or $full.Substring(2).Contains(':')) {
        throw 'Expected a local, non-root Windows path.'
    }
    foreach ($component in $full.Substring(3).Split('\')) {
        if ($component -match '[ .]$') { throw 'Ambiguous Windows path component.' }
    }
    $cursor = $full
    while ($cursor) {
        try {
            $attributes = [IO.File]::GetAttributes($cursor)
            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Reparse points are not permitted in probe paths.'
            }
        } catch [IO.FileNotFoundException] {
            # Missing leaf/checkout is allowed; ancestors still require checks.
        } catch [IO.DirectoryNotFoundException] {
        }
        $parent = [IO.Directory]::GetParent($cursor)
        $cursor = if ($null -eq $parent) { $null } else { $parent.FullName }
    }
    return $full
}

function Test-AtOrBelow([string] $Child, [string] $Parent) {
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-Disjoint([string] $Left, [string] $Right) {
    if ((Test-AtOrBelow $Left $Right) -or (Test-AtOrBelow $Right $Left)) {
        throw 'Probe paths overlap (including an ancestor relationship).'
    }
}

function Assert-WeightPins($Weights) {
    if ($Weights -isnot [Collections.IDictionary] -or $Weights.Count -ne $expectedWeights.Count) {
        throw 'Unexpected model weight set in pin evidence.'
    }
    foreach ($name in $expectedWeights.Keys) {
        if ($Weights[$name] -cne $expectedWeights[$name]) { throw 'Model SHA-256 evidence mismatch.' }
    }
}

function Get-PackageStats([string] $Directory) {
    $pending = [Collections.Generic.Stack[IO.DirectoryInfo]]::new()
    $pending.Push([IO.DirectoryInfo]::new($Directory))
    [long] $bytes = 0
    [long] $count = 0
    while ($pending.Count -gt 0) {
        foreach ($entry in $pending.Pop().GetFileSystemInfos()) {
            if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'Frozen package contains a reparse point.'
            }
            if ($entry -is [IO.DirectoryInfo]) { $pending.Push($entry) }
            else { $bytes += $entry.Length; $count++ }
        }
    }
    return @{ package_bytes = $bytes; package_file_count = $count }
}

function Read-SmallJson([string] $Path, [long] $Limit) {
    $safe = Get-SafeFullPath $Path
    $file = Get-Item -LiteralPath $safe -Force
    if ($file.PSIsContainer -or $file.Length -gt $Limit) { throw 'JSON report absent or oversized.' }
    $value = [IO.File]::ReadAllText($safe) | ConvertFrom-Json -AsHashtable
    if ($value -isnot [Collections.IDictionary]) { throw 'JSON report must be an object.' }
    return $value
}

# Job membership covers descendants even after their parent exits. The entry
# waits on a gate until assignment succeeds, before any model/import work.
# Breakaway is not enabled, and closing the job is a final kill-on-close guard.
$nativeHelpers = @'
using System;
using System.ComponentModel;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
namespace KumaMerizoProbe {
    public sealed class ProcessJob : IDisposable {
        [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
            public long ProcessTime, JobTime;
            public uint Flags;
            public UIntPtr MinWorkingSet, MaxWorkingSet;
            public uint ActiveLimit;
            public UIntPtr Affinity;
            public uint Priority, Scheduling;
        }
        [StructLayout(LayoutKind.Sequential)] struct IoCounters {
            public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
        }
        [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
            public BasicLimits Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential)] struct Accounting {
            public long UserTime, KernelTime, PeriodUserTime, PeriodKernelTime;
            public uint PageFaults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits limits, uint length);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern bool QueryInformationJobObject(IntPtr job, int kind, out Accounting info, uint length, IntPtr returned);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)]
        static extern bool TerminateJobObject(IntPtr job, uint exitCode);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        IntPtr handle;
        static void Check(bool ok) { if (!ok) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        public ProcessJob() {
            handle = CreateJobObject(IntPtr.Zero, null);
            if (handle == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            var limits = new ExtendedLimits();
            limits.Basic.Flags = 0x00002000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            try { Check(SetInformationJobObject(handle, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>())); }
            catch { Dispose(); throw; }
        }
        public void Assign(Process process) { Check(AssignProcessToJobObject(handle, process.Handle)); }
        public uint ActiveProcesses {
            get {
                Accounting info;
                Check(QueryInformationJobObject(handle, 1, out info, (uint)Marshal.SizeOf<Accounting>(), IntPtr.Zero));
                return info.ActiveProcesses;
            }
        }
        public void Terminate() { Check(TerminateJobObject(handle, 2)); }
        public void Dispose() {
            if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
        }
    }
    public static class OutputSink {
        // Drain both streams concurrently into a fixed-size buffer, never a log
        // or unbounded ReadToEnd string. Keep at most 2048 stderr characters so
        // a bootloader failure before Python starts remains diagnosable.
        sealed class TailBuffer {
            readonly object sync = new object();
            string value = "";
            public void Append(char[] buffer, int count) {
                lock (sync) {
                    string combined = value + new string(buffer, 0, count);
                    value = combined.Length <= 2048 ? combined : combined.Substring(combined.Length - 2048);
                }
            }
            public string Value { get { lock (sync) return value; } }
        }
        static readonly ConcurrentDictionary<StreamReader, TailBuffer> tails =
            new ConcurrentDictionary<StreamReader, TailBuffer>();
        public static Task<long> Drain(StreamReader reader) { return Drain(reader, false); }
        public static string Tail(StreamReader reader) {
            TailBuffer tail;
            return tails.TryGetValue(reader, out tail) ? tail.Value : "";
        }
        public static async Task<long> Drain(StreamReader reader, bool keepTail) {
            TailBuffer tail = keepTail ? new TailBuffer() : null;
            if (keepTail) tails[reader] = tail;
            char[] buffer = new char[4096];
            long count = 0;
            int read;
            while ((read = await reader.ReadAsync(buffer, 0, buffer.Length).ConfigureAwait(false)) != 0) {
                count += read;
                if (tail != null) tail.Append(buffer, read);
            }
            return count;
        }
    }
}
'@

function Stop-ProbeTree($Process, $Job, [bool] $Assigned, [string] $Taskkill) {
    # taskkill is an explicit absolute system executable, never PATH-resolved.
    # The job additionally kills descendants whose original parent has exited.
    if (-not $Process.HasExited) {
        $killInfo = [Diagnostics.ProcessStartInfo]::new()
        $killInfo.FileName = $Taskkill
        $killInfo.UseShellExecute = $false
        $killInfo.CreateNoWindow = $true
        $killInfo.RedirectStandardOutput = $true
        $killInfo.RedirectStandardError = $true
        foreach ($argument in @('/PID', [string] $Process.Id, '/T', '/F')) {
            $killInfo.ArgumentList.Add($argument)
        }
        $killer = $null
        try {
            $killer = [Diagnostics.Process]::Start($killInfo)
            $discardOut = [KumaMerizoProbe.OutputSink]::Drain($killer.StandardOutput)
            $discardErr = [KumaMerizoProbe.OutputSink]::Drain($killer.StandardError)
            if (-not $killer.WaitForExit(5000)) {
                $killer.Kill($true)
                [void] $killer.WaitForExit(1000)
            }
        } catch {
            # Job termination still runs if taskkill itself cannot start.
        } finally {
            if ($null -ne $killer) { $killer.Dispose() }
        }
    }
    if ($Assigned) { $Job.Terminate() }
    if (-not $Process.HasExited) { $Process.Kill($true) }
    $deathWatch = [Diagnostics.Stopwatch]::StartNew()
    do {
        $rootExited = $Process.WaitForExit(100)
        $active = if ($Assigned) { $Job.ActiveProcesses } else { 0 }
        if ($rootExited -and $active -eq 0) { return $true }
        Start-Sleep -Milliseconds 100
    } while ($deathWatch.Elapsed.TotalSeconds -lt 10)
    return $false
}

$report = [ordered]@{
    status = 'failed'
    scope = 'frozen_native_windows_cpu_public_fixture_smoke_only'
    timeout_seconds = $timeoutSeconds
    source_removed = $false
    process_started = $false
    job_assigned_before_inference = $false
    process_tree_termination_verified = $null
    runtime_directory_removed = $null
    system_python_physically_removed = $false
    not_verified = @('absence of system Python installation', 'KUMA integration', 'native GUI',
        'installer', 'redistribution rights', 'biological accuracy')
}
$resultPath = $null
$runtimeDirectory = $null
$runtimeOwned = $false
$source = $null
$process = $null
$job = $null
$stdout = $null
$stderr = $null
$stderrTail = ''
$jobAssigned = $false
$watch = [Diagnostics.Stopwatch]::new()
$exitCode = 1

try {
    if (-not $IsWindows) { throw 'This probe requires native Windows PowerShell 7.' }
    $package = Get-SafeFullPath $PackageDirectory
    $fixturePath = Get-SafeFullPath $Fixture
    $pinPath = Get-SafeFullPath $PinReport
    $resultDirectoryPath = Get-SafeFullPath $ResultDirectory
    $repo = Get-SafeFullPath (Join-Path $PSScriptRoot '../..')
    Assert-Disjoint $resultDirectoryPath $package
    [void] [IO.Directory]::CreateDirectory($resultDirectoryPath)
    $resultPath = Get-SafeFullPath (Join-Path $resultDirectoryPath 'frozen-windows-cpu.json')
    if ($resultPath.Equals($pinPath, [StringComparison]::OrdinalIgnoreCase) -or
        $resultPath.Equals($fixturePath, [StringComparison]::OrdinalIgnoreCase)) {
        $resultPath = $null
        throw 'Result file must not overwrite build evidence or the public fixture.'
    }
    # Erase stale success evidence before validating a new run.
    [IO.File]::WriteAllText($resultPath, '{"status":"started"}')

    $pins = Read-SmallJson $pinPath 64KB
    if ($pins.status -cne 'built' -or $pins.verified_before_build -isnot [bool] -or
        -not $pins.verified_before_build -or $pins.source_commit -cne $expectedCommit) {
        throw 'Build did not record verified official source before freezing.'
    }
    Assert-WeightPins $pins.weights_sha256
    if (-not [IO.Path]::IsPathFullyQualified($pins.source_directory) -or
        -not [IO.Path]::IsPathFullyQualified($pins.package_directory)) {
        throw 'Build evidence paths must be absolute.'
    }
    $source = Get-SafeFullPath $pins.source_directory
    $builtPackage = Get-SafeFullPath $pins.package_directory
    if (-not $package.Equals($builtPackage, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Package does not match build pin evidence.'
    }
    Assert-Disjoint $source $package
    Assert-Disjoint $source $resultDirectoryPath
    if (Test-Path -LiteralPath $source) { throw 'Workflow must remove the official source checkout before launch.' }
    $report.source_removed = $true
    $report.source_commit = $expectedCommit
    $report.weights_sha256 = $expectedWeights
    $report.input_sha256 = $expectedInput
    if ((Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedInput) {
        throw 'Only the pinned public 1UBQ input is permitted.'
    }
    $stats = Get-PackageStats $package
    if ($stats.package_bytes -ne $pins.package_bytes -or $stats.package_file_count -ne $pins.package_file_count) {
        throw 'Package size/file count differs from build evidence.'
    }
    $report.package_bytes = $stats.package_bytes
    $report.package_file_count = $stats.package_file_count
    $exe = Get-SafeFullPath (Join-Path $package 'merizo-frozen-smoke.exe')
    if (-not [IO.File]::Exists($exe)) { throw 'Frozen executable is missing.' }

    $tempRoot = Get-SafeFullPath ([IO.Path]::GetTempPath())
    $runtimeDirectory = Get-SafeFullPath (Join-Path $tempRoot ('kuma merizo frozen ' + [Guid]::NewGuid().ToString('N')))
    foreach ($other in @($repo, $package, $source, $resultDirectoryPath)) {
        Assert-Disjoint $runtimeDirectory $other
    }
    [void] (New-Item -Path $runtimeDirectory -ItemType Directory)
    $runtimeOwned = $true
    $runtimeFixture = Join-Path $runtimeDirectory 'public input with spaces.pdb'
    $runtimeReport = Join-Path $runtimeDirectory 'frozen-runtime.json'
    $gate = Join-Path $runtimeDirectory 'job assigned gate'
    [IO.File]::Copy($fixturePath, $runtimeFixture, $false)
    $report.working_directory_has_spaces = $runtimeDirectory.Contains(' ')
    $report.working_directory_outside_repository_source_package = $true
    $report.copied_inputs = @('pinned_public_1ubq_fixture_only')

    $systemRoot = [Environment]::GetFolderPath([Environment+SpecialFolder]::Windows)
    $systemDirectory = [Environment]::SystemDirectory
    $taskkill = Join-Path $systemDirectory 'taskkill.exe'
    if (-not [IO.File]::Exists($taskkill)) { throw 'System taskkill executable is unavailable.' }
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $exe
    $info.WorkingDirectory = $runtimeDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @('--fixture', $runtimeFixture, '--output', $runtimeReport)) {
        $info.ArgumentList.Add($argument)
    }
    $removedPythonNames = @($info.Environment.Keys | Where-Object { $_ -match '^(PYTHON|CONDA|VIRTUAL_ENV|_PYI|PYINSTALLER)' } | Sort-Object)
    $info.Environment.Clear()
    foreach ($name in @('OS', 'PROCESSOR_ARCHITECTURE', 'PROCESSOR_IDENTIFIER', 'NUMBER_OF_PROCESSORS')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($null -ne $value) { $info.Environment[$name] = $value }
    }
    $info.Environment['SystemRoot'] = $systemRoot
    $info.Environment['WINDIR'] = $systemRoot
    $info.Environment['COMSPEC'] = Join-Path $systemDirectory 'cmd.exe'
    $info.Environment['PATH'] = $systemDirectory + ';' + $systemRoot
    foreach ($name in @('TEMP', 'TMP', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'MPLCONFIGDIR', 'TORCH_HOME', 'XDG_CACHE_HOME')) {
        $info.Environment[$name] = $runtimeDirectory
    }
    foreach ($name in @('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS')) { $info.Environment[$name] = '1' }
    $info.Environment['MPLBACKEND'] = 'Agg'
    $info.Environment['CUDA_VISIBLE_DEVICES'] = ''
    $info.Environment['KUMA_MERIZO_START_GATE'] = $gate
    $report.sanitized_env = @{
        inherited_environment_cleared = $true
        path = $info.Environment['PATH']
        python_environment_names_removed = $removedPythonNames
        python_environment_variables_present = @($info.Environment.Keys | Where-Object { $_ -match '^PYTHON' })
        permitted_names = @($info.Environment.Keys | Sort-Object)
        temporary_user_and_cache_directories = $true
    }

    Add-Type -TypeDefinition $nativeHelpers
    $job = [KumaMerizoProbe.ProcessJob]::new()
    # Recheck immediately before launch: deleting source is the workflow's job.
    if (Test-Path -LiteralPath $source) {
        $report.source_removed = $false
        throw 'Official source reappeared before launch.'
    }
    $watch.Start()
    $process = [Diagnostics.Process]::Start($info)
    $report.process_started = $true
    $stdout = [KumaMerizoProbe.OutputSink]::Drain($process.StandardOutput)
    $stderr = [KumaMerizoProbe.OutputSink]::Drain($process.StandardError, $true)
    $job.Assign($process)
    $jobAssigned = $true
    $report.job_assigned_before_inference = $true
    [IO.File]::WriteAllText($gate, 'ready')

    [long] $sampledPeak = 0
    [long] $reportedPeak = 0
    $timedOut = $false
    while (-not $process.HasExited) {
        $process.Refresh()
        try {
            $sampledPeak = [Math]::Max($sampledPeak, $process.WorkingSet64)
            $reportedPeak = [Math]::Max($reportedPeak, $process.PeakWorkingSet64)
        } catch [InvalidOperationException] {
            if (-not $process.HasExited) { throw }
        }
        if ($watch.Elapsed.TotalSeconds -ge $timeoutSeconds) { $timedOut = $true; break }
        [void] $process.WaitForExit(100)
    }
    $report.sampled_peak_working_set_bytes = $sampledPeak
    $report.process_peak_working_set_bytes = $reportedPeak
    $report.peak_working_set_bytes = [Math]::Max($sampledPeak, $reportedPeak)
    if (-not $timedOut) {
        # Root exit and job accounting can become visible a few ticks apart.
        $accountingWatch = [Diagnostics.Stopwatch]::StartNew()
        while ($job.ActiveProcesses -gt 0 -and $accountingWatch.Elapsed.TotalSeconds -lt 1) {
            Start-Sleep -Milliseconds 50
        }
    }
    if ($timedOut) {
        $report.status = 'timed_out'
        $report.watchdog_triggered = $true
        $exitCode = 2
    } elseif ($process.ExitCode -ne 0) {
        $report.exit_code = $process.ExitCode
        if ([IO.File]::Exists($runtimeReport)) {
            try {
                $failedRuntime = Read-SmallJson $runtimeReport 1MB
                $report.runtime = @{ status = $failedRuntime.status; error = $failedRuntime.error }
            }
            catch { $report.runtime_report_error = 'Failed runtime report was invalid or oversized.' }
        }
        throw 'Frozen executable failed; raw stdout/stderr are intentionally not retained.'
    } elseif ($job.ActiveProcesses -ne 0) {
        throw 'Frozen executable left live descendant processes.'
    } else {
        $runtime = Read-SmallJson $runtimeReport 1MB
        if ($runtime.status -cne 'passed' -or $runtime.source_commit -cne $expectedCommit -or
            $runtime.input_sha256 -cne $expectedInput) { throw 'Frozen runtime evidence is incomplete.' }
        if ($runtime.frozen -isnot [bool] -or -not $runtime.frozen -or
            -not (Get-SafeFullPath $runtime.bundle_root).Equals($package, [StringComparison]::OrdinalIgnoreCase) -or
            -not (Get-SafeFullPath $runtime.package_directory).Equals($package, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Runtime did not confirm execution from the expected frozen bundle.'
        }
        Assert-WeightPins $runtime.weights_sha256
        $report.runtime = $runtime
        $report.status = 'passed'
        $exitCode = 0
    }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message.Substring(0, [Math]::Min(2000, $_.Exception.Message.Length))
    $exitCode = 1
} finally {
    if ($null -ne $process) {
        try {
            $terminated = if ($process.HasExited -and $jobAssigned -and $job.ActiveProcesses -eq 0) {
                $true
            } else { Stop-ProbeTree $process $job $jobAssigned $taskkill }
            $report.process_tree_termination_verified = $terminated -and $jobAssigned
            if (-not $report.process_tree_termination_verified) {
                throw 'Process tree termination could not be independently verified through job accounting.'
            }
            $report.exit_code = $process.ExitCode
            foreach ($stream in @(@('stdout', $stdout), @('stderr', $stderr))) {
                if ($null -ne $stream[1] -and $stream[1].Wait(1000)) {
                    $report[$stream[0] + '_characters_drained'] = $stream[1].Result
                }
            }
        } catch {
            $report.status = 'cleanup_failed'
            $report.process_tree_termination_verified = $false
            $report.cleanup_error = $_.Exception.Message
            $exitCode = 3
        } finally {
            try { $stderrTail = [KumaMerizoProbe.OutputSink]::Tail($process.StandardError) }
            catch { $stderrTail = '' }
            if ($null -ne $job) { $job.Dispose(); $job = $null }
            $process.Dispose()
        }
    }
    if ($null -ne $job) { $job.Dispose() }
    $watch.Stop()
    $report.elapsed_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
    if ($runtimeOwned) {
        try {
            # The only tree this script deletes is the fresh directory it made.
            [void] (Get-SafeFullPath $runtimeDirectory)
            Remove-Item -LiteralPath $runtimeDirectory -Recurse -Force
            $report.runtime_directory_removed = -not (Test-Path -LiteralPath $runtimeDirectory)
            if (-not $report.runtime_directory_removed) { throw 'Temporary runtime directory remains.' }
        } catch {
            $report.runtime_directory_removed = $false
            $report.status = 'cleanup_failed'
            $report.cleanup_error = $_.Exception.Message
            $exitCode = 3
        }
    }
    if ($report.status -cne 'passed' -and $stderrTail.Length -gt 0) {
        $report.stderr_tail = $stderrTail
    }
    if ($null -ne $resultPath) {
        try {
            $json = ($report | ConvertTo-Json -Depth 30) + [Environment]::NewLine
            if ([Text.Encoding]::UTF8.GetByteCount($json) -gt $maxReportBytes) {
                $json = '{"status":"failed","error":"Combined report exceeded 2 MiB limit."}'
                $exitCode = 1
            }
            [IO.File]::WriteAllText($resultPath, $json, [Text.UTF8Encoding]::new($false))
        } catch {
            [Console]::Error.WriteLine('Could not save the small frozen-runtime report.')
            $exitCode = 1
        }
    }
}
exit $exitCode
