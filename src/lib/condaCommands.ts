// Helpers for routing conda-related commands through the embedded PTY terminal.
//
// Sentinel format (matches SetupTerminal.onSentinel("__EP_", ...)):
//   __EP_<STEP_ID>_OK__
//   __EP_<STEP_ID>_FAIL__:<exit_code>
//
// Assumptions:
// - Tauri's @tauri-apps/plugin-os exposes only async APIs. Synchronous shell
//   detection here uses navigator.userAgent / navigator.platform, which is
//   sufficient for the wizard (renderer always runs in a browser context).
// - condaExePath may contain spaces, so it must be quoted in both shells.
// - On POSIX, `$SHELL` can be empty in some sandboxed environments. In that
//   case `basename "$SHELL"` is empty and `conda init` will fail, which the
//   sentinel surfaces as FAIL (acceptable behavior for now).

export type ShellKind = "powershell" | "bash";

export function detectShellKind(): ShellKind {
  if (typeof navigator !== "undefined") {
    const ua = (navigator.userAgent || "").toLowerCase();
    const platform = (navigator.platform || "").toLowerCase();
    if (ua.includes("windows") || platform.includes("win")) return "powershell";
  }
  return "bash";
}

export function wrapWithSentinel(
  cmd: string,
  stepId: string,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    // $LASTEXITCODE preserves the native exit code from the wrapped command.
    // Prepend an echo line so the user can see which step is running.
    const psPreview = cmd.replace(/"/g, '`"');
    return `Write-Host ">>> [${stepId}] ${psPreview}" -ForegroundColor Cyan; & { ${cmd} ; if ($LASTEXITCODE -eq 0) { Write-Host "__EP_${stepId}_OK__" } else { Write-Host "__EP_${stepId}_FAIL__:$LASTEXITCODE" } }`;
  }
  // bash/zsh: capture $? on the failure branch.
  const shPreview = cmd.replace(/"/g, '\\"');
  return `echo ">>> [${stepId}] ${shPreview}" ; { ${cmd}; } && echo "__EP_${stepId}_OK__" || echo "__EP_${stepId}_FAIL__:$?"`;
}

export function buildInitShellCommand(
  condaExePath: string,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    return `& "${condaExePath}" init powershell`;
  }
  // POSIX: pick the user shell basename, falling back to bash via conda's own handling.
  return `"${condaExePath}" init "$(basename "$SHELL")"`;
}

// -----------------------------------------------------------------------------
// Create-env command builders (Step 2 migration)
// -----------------------------------------------------------------------------
// Python sidecar `_PIP_PACKAGES` (python-core/sidecar/conda_setup.py lines 63~85) mirror.
// SSOT lives in python-core/sidecar/conda_setup.py. When changing either side,
// keep the two lists in sync.
// TODO(step4): consolidate via codegen or a `conda.get_packages` sidecar RPC.
export const PIP_PACKAGES = [
  "numpy<2.0",
  "pandas",
  "openpyxl",
  "scikit-learn",
  "scikit-learn-extra",
  "xgboost",
  "matplotlib",
  "seaborn",
  "biopython",
  "scipy",
  "torch",
  "fair-esm",
  // Note: EvolvePro source is NOT pip-installed. The upstream repo lacks
  // evolvepro/__init__.py so pip produces an empty wheel. Use
  // buildEvolveProInstallCommand to download the archive and register it
  // via a .pth file (mirrors sidecar _install_evolvepro_source).
] as const;

// SSOT mirrors python-core/sidecar/conda_setup.py _install_evolvepro_source.
const EVOLVEPRO_SOURCE_URL =
  "https://github.com/mat10d/EvolvePro/archive/refs/heads/main.zip";

export const ENV_NAME = "evolvepro"; // must match sidecar conda_setup.py

export interface CondaPathInfo {
  // Windows: <prefix>\Scripts\conda.exe, POSIX: <prefix>/bin/conda
  condaExe: string;
  // Windows: <prefix>\envs\<env>\python.exe, POSIX: <prefix>/envs/<env>/bin/python
  envPython: string;
}

// Assumptions:
// - condaExe layout follows Rust miniforge_conda_exe (lib.rs ~ line 494-500):
//   POSIX `<prefix>/bin/conda`, Windows `<prefix>\Scripts\conda.exe`.
// - env_python is derived from the default conda layout. Custom env prefixes
//   would break the derivation, but the wizard only supports the default
//   prefix today.
export function deriveEnvPython(
  condaExe: string,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    const prefix = condaExe.replace(/[\\/]Scripts[\\/]conda(?:\.exe)?$/i, "");
    return `${prefix}\\envs\\${ENV_NAME}\\python.exe`;
  }
  const prefix = condaExe.replace(/\/bin\/conda$/, "");
  return `${prefix}/envs/${ENV_NAME}/bin/python`;
}

export function buildCreateEnvCommand(
  condaExe: string,
  shell: ShellKind = detectShellKind(),
): string {
  const quoted = shell === "powershell" ? `& "${condaExe}"` : `"${condaExe}"`;
  return `${quoted} create -n ${ENV_NAME} -c conda-forge python=3.11 pip --solver=libmamba -y`;
}

export function buildPipInstallCommand(
  envPython: string,
  shell: ShellKind = detectShellKind(),
): string {
  const quotedPython =
    shell === "powershell" ? `& "${envPython}"` : `"${envPython}"`;
  // pip install args: every package quoted to keep URLs intact. The list is a
  // single token sequence and works in both shells.
  const args = PIP_PACKAGES.map((p) => `"${p}"`).join(" ");
  return `${quotedPython} -m pip install ${args}`;
}

// EvolvePro source installer. The upstream archive has no evolvepro/__init__.py
// so pip yields an empty wheel; instead, download the archive and register the
// extracted directory in site-packages via a .pth file. This mirrors the
// sidecar `_install_evolvepro_source` (python-core/sidecar/conda_setup.py).
//
// Assumptions:
// - The inline Python script uses only double quotes internally so it can be
//   safely wrapped in single quotes by both PowerShell and bash.
// - Network access via urllib is available; failures surface as non-zero exit
//   and are caught by the sentinel FAIL branch.
// - sysconfig.get_paths()["purelib"] returns the active env's site-packages
//   because the command is invoked with the env's own python interpreter.
export function buildEvolveProInstallCommand(
  envPython: string,
  shell: ShellKind = detectShellKind(),
): string {
  // Python script. Uses double quotes freely; encoded as base64 to avoid shell
  // quoting issues (PowerShell strips inner double quotes from python.exe argv
  // when wrapped in single quotes).
  const pythonScript = [
    "import urllib.request, zipfile, io, sys, sysconfig, shutil",
    "from pathlib import Path",
    `URL = "${EVOLVEPRO_SOURCE_URL}"`,
    "env_root = Path(sys.prefix)",
    `src = env_root / "evolvepro-src"`,
    `print("[evolvepro] downloading source archive...")`,
    "data = urllib.request.urlopen(URL, timeout=300).read()",
    `print("[evolvepro] downloaded", len(data), "bytes; extracting...")`,
    "shutil.rmtree(src, ignore_errors=True)",
    "src.mkdir(parents=True)",
    "zipfile.ZipFile(io.BytesIO(data)).extractall(src)",
    `ex = src / "EvolvePro-main"`,
    "ex = ex if ex.is_dir() else next((p for p in src.iterdir() if p.is_dir()), None)",
    `assert ex is not None, "extracted archive contained no directories"`,
    `sp = Path(sysconfig.get_paths()["purelib"])`,
    `pth = sp / "evolvepro.pth"`,
    `pth.write_text(str(ex) + chr(10), encoding="utf-8")`,
    `print("[evolvepro] installed at", ex)`,
    `print("[evolvepro] .pth registered at", pth)`,
  ].join("\n");

  // UTF-8 safe base64 encoding (browser TextEncoder + btoa).
  const bytes = new TextEncoder().encode(pythonScript);
  let binStr = "";
  for (const b of bytes) binStr += String.fromCharCode(b);
  const b64 = btoa(binStr);

  // Bootstrap: short, quoting-safe (only single quotes around base64 payload).
  const bootstrap = `import base64;exec(base64.b64decode('${b64}').decode('utf-8'))`;

  if (shell === "powershell") {
    return `& "${envPython}" -c "${bootstrap}"`;
  }
  return `"${envPython}" -c "${bootstrap}"`;
}

export function buildVerifyCommand(
  envPython: string,
  shell: ShellKind = detectShellKind(),
): string {
  const pythonScript = `import evolvepro, esm, torch, numpy, pandas, sklearn, xgboost\nprint("OK")`;
  const bytes = new TextEncoder().encode(pythonScript);
  let binStr = "";
  for (const b of bytes) binStr += String.fromCharCode(b);
  const b64 = btoa(binStr);
  const bootstrap = `import base64;exec(base64.b64decode('${b64}').decode('utf-8'))`;
  if (shell === "powershell") {
    return `& "${envPython}" -c "${bootstrap}"`;
  }
  return `"${envPython}" -c "${bootstrap}"`;
}

export function buildEnvRemoveCommand(
  condaExe: string,
  shell: ShellKind = detectShellKind(),
): string {
  const quoted = shell === "powershell" ? `& "${condaExe}"` : `"${condaExe}"`;
  return `${quoted} env remove -n ${ENV_NAME} -y`;
}

// -----------------------------------------------------------------------------
// Miniforge install command builders (Step 3 migration)
// -----------------------------------------------------------------------------
// SSOT for the URL prefix lives in src-tauri/src/lib.rs (MINIFORGE_URL_PREFIX
// around line 450). When changing either side, keep the two in sync.
const MINIFORGE_URL_PREFIX =
  "https://github.com/conda-forge/miniforge/releases/latest/download/";

export interface MiniforgePlatform {
  installerName: string;
  isSh: boolean;
  // Windows: %USERPROFILE%\miniforge3, POSIX: $HOME/miniforge3.
  // The literal is left unexpanded so the PTY shell expands it at runtime.
  installPrefix: string;
  // POSIX: $HOME/.cache/evolvepro/miniforge-installer.sh
  // Windows: $env:LOCALAPPDATA\evolvepro\miniforge-installer.exe
  installerPath: string;
}

// Assumptions:
// - macOS arm64 vs x86_64 detection via navigator is best-effort. Apple Silicon
//   may still report "Intel Mac OS X" in userAgent; a wrong installer choice
//   surfaces as a FAIL sentinel from the install step. Tighter detection
//   requires the async Tauri os plugin (Step 4 follow-up).
// - $HOME / $env:USERPROFILE / $env:LOCALAPPDATA are left as literals so the
//   PTY shell expands them. Do not pre-expand on the renderer side.
export function detectMiniforgePlatform(
  shell: ShellKind = detectShellKind(),
): MiniforgePlatform {
  if (shell === "powershell") {
    return {
      installerName: "Miniforge3-Windows-x86_64.exe",
      isSh: false,
      installPrefix: "$env:USERPROFILE\\miniforge3",
      installerPath: "$env:LOCALAPPDATA\\evolvepro\\miniforge-installer.exe",
    };
  }
  const ua =
    typeof navigator !== "undefined"
      ? (navigator.userAgent || "").toLowerCase()
      : "";
  const platformStr =
    typeof navigator !== "undefined"
      ? (navigator.platform || "").toLowerCase()
      : "";
  const isMac = ua.includes("mac") || platformStr.includes("mac");
  const isArm =
    ua.includes("arm") ||
    platformStr.includes("arm") ||
    ua.includes("aarch64");
  let installerName: string;
  if (isMac) {
    installerName = isArm
      ? "Miniforge3-MacOSX-arm64.sh"
      : "Miniforge3-MacOSX-x86_64.sh";
  } else {
    installerName = isArm
      ? "Miniforge3-Linux-aarch64.sh"
      : "Miniforge3-Linux-x86_64.sh";
  }
  return {
    installerName,
    isSh: true,
    installPrefix: "$HOME/miniforge3",
    installerPath: "$HOME/.cache/evolvepro/miniforge-installer.sh",
  };
}

export function buildDownloadCommand(
  plat: MiniforgePlatform,
  shell: ShellKind = detectShellKind(),
): string {
  const url = `${MINIFORGE_URL_PREFIX}${plat.installerName}`;
  if (shell === "powershell") {
    // curl.exe preferred (shows a progress bar), Invoke-WebRequest fallback.
    // Cache dir is created lazily.
    return `& { New-Item -ItemType Directory -Force -Path (Split-Path -Parent "${plat.installerPath}") | Out-Null; if (Get-Command curl.exe -ErrorAction SilentlyContinue) { curl.exe -fL -o "${plat.installerPath}" "${url}" } else { Invoke-WebRequest -Uri "${url}" -OutFile "${plat.installerPath}" -UseBasicParsing } }`;
  }
  return `mkdir -p "$(dirname "${plat.installerPath}")" && curl -fL --progress-bar -o "${plat.installerPath}" "${url}"`;
}

export function buildSilentInstallCommand(
  plat: MiniforgePlatform,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    // Flags follow the conda-forge/miniforge Windows README for unattended
    // install. Calling the exe directly (instead of Start-Process) lets any
    // stdout flow through the PTY. /S is NSIS silent so output is minimal:
    // prepend a heads-up so users do not think the wizard is stuck.
    return `Write-Host "Installing Miniforge... this may take 3-5 minutes (silent installer, minimal output)" -ForegroundColor Yellow; & "${plat.installerPath}" /InstallationType=JustMe /RegisterPython=0 /S /D=${plat.installPrefix}`;
  }
  // -b batch (no prompt), -u update if exists, -p prefix.
  return `echo "Installing Miniforge... this may take 3-5 minutes"; bash "${plat.installerPath}" -b -u -p "${plat.installPrefix}"`;
}

// Prefix conflict check. Emits one of three OK sentinels so the wizard can
// branch without changing SetupTerminal's sentinel regex:
//   __EP_PREFIX_EXIST_OK__   conda binary already present
//   __EP_PREFIX_DIRTY_OK__   prefix directory exists but no conda binary
//   __EP_PREFIX_ABSENT_OK__  no directory at all
export function buildPrefixCheckCommand(
  plat: MiniforgePlatform,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    const condaPath = `${plat.installPrefix}\\Scripts\\conda.exe`;
    return `if (Test-Path "${condaPath}") { Write-Host "__EP_PREFIX_EXIST_OK__" } elseif (Test-Path "${plat.installPrefix}") { Write-Host "__EP_PREFIX_DIRTY_OK__" } else { Write-Host "__EP_PREFIX_ABSENT_OK__" }`;
  }
  const condaPath = `${plat.installPrefix}/bin/conda`;
  return `if [ -f "${condaPath}" ]; then echo __EP_PREFIX_EXIST_OK__; elif [ -d "${plat.installPrefix}" ]; then echo __EP_PREFIX_DIRTY_OK__; else echo __EP_PREFIX_ABSENT_OK__; fi`;
}

// Best-effort cleanup after a cancelled install. Removes both the partial
// installer file and any prefix directory the installer may have created.
// Either path missing is fine, so the command is wrapped in `& { ... }` /
// `;` to keep $LASTEXITCODE at 0 unless both removals genuinely failed.
export function buildInstallCancelCleanupCommand(
  plat: MiniforgePlatform,
  shell: ShellKind = detectShellKind(),
): string {
  if (shell === "powershell") {
    return `& { if (Test-Path "${plat.installerPath}") { Remove-Item "${plat.installerPath}" -Force }; if (Test-Path "${plat.installPrefix}") { Remove-Item "${plat.installPrefix}" -Recurse -Force } }`;
  }
  return `rm -f "${plat.installerPath}"; rm -rf "${plat.installPrefix}"; true`;
}
