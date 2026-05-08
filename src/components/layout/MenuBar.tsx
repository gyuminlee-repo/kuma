import { useState, useEffect } from "react";
import { notificationPermissionGranted, requestNotificationPermission } from "../../lib/notify";
import { useAppStore } from "../../store/appStore";
import { generateDiagnosticsBundle } from "../../lib/diagnostics";
import { revealInOSFolder } from "../../lib/openFolder";
import { useKumaProject } from "../../state/projectContext";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "../ui/dropdown-menu";
import { getCrashLog } from "../../lib/crashLog";
import { CrashLogDialog } from "../dialogs/CrashLogDialog";
import {
  handleExportExcel,
  handleExportMappingWithParams,
  handleSaveWorkspace,
  handleLoadWorkspace,
  handleOpenSequence,
  executeMigrateAndLoad,
  MIGRATE_DIALOG_CLOSED,
} from "./export-handlers";
import { WorkspaceMigrateDialog } from "../dialogs/WorkspaceMigrateDialog";
import type { MigrateDialogState } from "../dialogs/WorkspaceMigrateDialog";
import { MappingExportDialog } from "../dialogs/MappingExportDialog";
import { SubtoolMenuBar } from "./SubtoolMenuBar";
import { LocaleToggle } from "../ui/LocaleToggle";
import { browseFile } from "../../lib/file-utils";
import { loadManifestFromFile } from "../../lib/runManifest";
import type { RunManifest } from "../../lib/runManifest";
import { verifyInputs } from "../../lib/reRun";
import type { InputVerifyResult } from "../../lib/reRun";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { resolveResource } from "@tauri-apps/api/path";
import { ReRunManifestDialog } from "../dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "../dialogs/ManifestDiffDialog";
import { checkForUpdates, downloadAndInstall, type UpdateCheckResult } from "../../lib/updater";
import type { Update } from "@tauri-apps/plugin-updater";
import { invoke } from "@tauri-apps/api/core";
import { killSidecar } from "../../lib/ipc";

const MOD_KEY = navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

/** 메뉴 트리거 공통 클래스 (계획서 §6.1 권장) */
const TRIGGER_CLS =
  "h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast text-caption font-medium text-foreground/80";

export function MenuBar() {
  const project = useKumaProject();
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const isExporting = useAppStore((s) => s.isExporting);
  const isDesigning = useAppStore((s) => s.isDesigning);
  const loadSampleData = useAppStore((s) => s.loadSampleData);
  const offlineMode = useAppStore((s) => s.offlineMode);
  const setOfflineMode = useAppStore((s) => s.setOfflineMode);
  const networkConsentGranted = useAppStore((s) => s.networkConsentGranted);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [crashCopied, setCrashCopied] = useState(false);
  const [bibtexCopied, setBibtexCopied] = useState(false);
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);
  const [crashLogOpen, setCrashLogOpen] = useState(false);
  const [mappingDialogOpen, setMappingDialogOpen] = useState(false);
  const [mappingDialogFormat, setMappingDialogFormat] = useState<"echo" | "janus">("echo");
  // §20 Citation & Licensing: NOTICE.md from bundled resources
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeLoading, setNoticeLoading] = useState(false);

  // §12 Reproducibility: manifest 파일 picker
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);
  const [notifyPermission, setNotifyPermission] = useState<boolean | null>(null);

  // §12 Reproducibility: manifest diff 모달 상태
  const [diffManifestA, setDiffManifestA] = useState<RunManifest | null>(null);
  const [diffManifestB, setDiffManifestB] = useState<RunManifest | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  // §9 Versioning & Updates
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [updateInstalling, setUpdateInstalling] = useState(false);

  // §11 Build & Distribution: codesign status (lazy-loaded when About opens)
  const [codesignStatus, setCodesignStatus] = useState<string | null>(null);

  useEffect(() => {
    void notificationPermissionGranted().then(setNotifyPermission);
  }, []);

  // §20: Load NOTICE.md from Tauri resources when About dialog opens.
  // Fails gracefully: if the file is absent (dev mode or pre-release build),
  // noticeText stays null and the placeholder message is shown instead.
  useEffect(() => {
    if (!aboutOpen || noticeText !== null) return;
    setNoticeLoading(true);
    void (async () => {
      try {
        const resourcePath = await resolveResource("resources/NOTICE.md");
        const text = await readTextFile(resourcePath);
        setNoticeText(text);
      } catch {
        // NOTICE.md not bundled in this build — fallback message shown below
        setNoticeText(null);
      } finally {
        setNoticeLoading(false);
      }
    })();
  }, [aboutOpen, noticeText]);

  // §11 Build & Distribution: load codesign status once when About opens
  useEffect(() => {
    if (!aboutOpen || codesignStatus !== null) return;
    void invoke<string>("get_codesign_status")
      .then((s) => setCodesignStatus(s))
      .catch(() => setCodesignStatus("unknown"));
  }, [aboutOpen, codesignStatus]);

  async function handleEnableNotifications() {
    const granted = await requestNotificationPermission();
    setNotifyPermission(granted);
  }
  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);

  // §14 Migration dialog state
  const [migrateDialog, setMigrateDialog] = useState<MigrateDialogState>(MIGRATE_DIALOG_CLOSED);
  const [migratePending, setMigratePending] = useState<Record<string, unknown> | null>(null);
  const [migrateLoading, setMigrateLoading] = useState(false);

  async function handleOpenManifest() {
    await browseFile(
      [{ name: "Run manifest", extensions: ["json"] }],
      async (path: string) => {
        try {
          const manifest = await loadManifestFromFile(path);
          const verify = await verifyInputs(manifest);
          setReRunVerify(verify);
          setReRunManifest(manifest);
        } catch (err) {
          useAppStore.setState({ statusMessage: `Manifest 로드 실패: ${String(err)}` });
        }
      },
    );
  }

  // §12 Reproducibility: 두 manifest 파일 picker (A → B 순차 선택)
  async function handleCompareManifests() {
    let manifestA: RunManifest | null = null;

    // 첫 번째 파일 (A)
    await browseFile(
      [{ name: "Run manifest A", extensions: ["json"] }],
      async (pathA: string) => {
        try {
          manifestA = await loadManifestFromFile(pathA);
        } catch (err) {
          useAppStore.setState({ statusMessage: `Manifest A 로드 실패: ${String(err)}` });
        }
      },
    );

    if (!manifestA) return;

    // 두 번째 파일 (B) — manifestA 를 로컬 const 로 캡처 (TS narrowing 유지)
    const capturedA = manifestA;
    await browseFile(
      [{ name: "Run manifest B", extensions: ["json"] }],
      async (pathB: string) => {
        try {
          const manifestB = await loadManifestFromFile(pathB);
          setDiffManifestA(capturedA);
          setDiffManifestB(manifestB);
          setDiffOpen(true);
        } catch (err) {
          useAppStore.setState({ statusMessage: `Manifest B 로드 실패: ${String(err)}` });
        }
      },
    );
  }

  const KURO_BIBTEX = `@software{kuro_TBD,
  title  = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

  async function handleCopyBibtex() {
    await navigator.clipboard.writeText(KURO_BIBTEX);
    setBibtexCopied(true);
    setTimeout(() => setBibtexCopied(false), 2000);
  }

  async function handleGenerateDiagnostics() {
    setDiagnosticsGenerating(true);
    setDiagnosticsError(null);
    try {
      const filePath = await generateDiagnosticsBundle();
      if (filePath) {
        await revealInOSFolder(filePath);
      }
    } catch (err) {
      setDiagnosticsError(err instanceof Error ? err.message : String(err));
    } finally {
      setDiagnosticsGenerating(false);
    }
  }

  async function handleCopyCrashLog() {
    const log = getCrashLog();
    if (log.length === 0) {
      setCrashCopied(false);
      return;
    }
    const text = log
      .map(
        (e) =>
          `[${e.timestamp}] ${e.component}: ${e.message}${e.stack ? "\n" + e.stack : ""}`,
      )
      .join("\n---\n");
    await navigator.clipboard.writeText(text);
    setCrashCopied(true);
    setTimeout(() => setCrashCopied(false), 2000);
  }

  // §9 Versioning: check for updates handler
  async function handleCheckForUpdates() {
    setUpdateChecking(true);
    setUpdateResult(null);
    try {
      const result = await checkForUpdates();
      setUpdateResult(result);
    } finally {
      setUpdateChecking(false);
    }
  }

  // §9 Versioning: download and install handler
  async function handleDownloadAndInstall(update: Update) {
    setUpdateInstalling(true);
    try {
      await downloadAndInstall(update);
    } catch (err: unknown) {
      setUpdateResult({
        status: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setUpdateInstalling(false);
    }
  }

  const menus = (
    <>
      {/* File 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>File</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={handleOpenSequence}>
            <span className="flex-1">Open Sequence...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}O</kbd>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void handleSaveWorkspace(project)}>
            <span className="flex-1">Save Workspace...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}S</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() =>
              void handleLoadWorkspace(project, (dialogState, rawWs) => {
                setMigratePending(rawWs);
                setMigrateDialog(dialogState);
              })
            }
          >
            Load Workspace...
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void handleOpenManifest()}>
            Open run manifest...
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void handleCompareManifests()}>
            Compare run manifests...
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {/* §1 Recovery: UI 상태 보존 sidecar 재시작. Zustand 스토어는 메모리에 유지됨 */}
          <DropdownMenuItem
            onClick={() => {
              const busy = isDesigning || isExporting;
              if (busy && !window.confirm("작업이 진행 중입니다. 그래도 sidecar를 재시작하시겠습니까?")) return;
              void killSidecar("kuro");
            }}
            disabled={false}
          >
            Restart Sidecar
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => handleExportExcel(project?.project_id)}
            disabled={!hasDesignResults || isExporting}
          >
            <span className="flex-1">Export Excel...</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}E</kbd>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => { setMappingDialogFormat("echo"); setMappingDialogOpen(true); }}
            disabled={!hasDesignResults || isExporting}
          >
            Export Echo Mapping...
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => { setMappingDialogFormat("janus"); setMappingDialogOpen(true); }}
            disabled={!hasDesignResults || isExporting}
          >
            Export JANUS Mapping...
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Help 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>Help</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={loadSampleData}>
            Load Sample Data
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => window.dispatchEvent(new CustomEvent("kuma:show-onboarding"))}>
            Show Onboarding
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setCrashLogOpen(true)}>
            View Crash Log
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
            About
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <SubtoolMenuBar
        label="Kuro"
        subtitle="Kernel for Upstream Recombination Oligodesign"
        menus={menus}
      />

      <CrashLogDialog open={crashLogOpen} onOpenChange={setCrashLogOpen} />

      <MappingExportDialog
        open={mappingDialogOpen}
        initialFormat={mappingDialogFormat}
        onOpenChange={setMappingDialogOpen}
        onExport={({ format, transferVol, bom }) => {
          setMappingDialogOpen(false);
          handleExportMappingWithParams(format, { transferVol, bom });
        }}
      />

      <Dialog
        open={aboutOpen}
        onOpenChange={(open: boolean) => {
          setAboutOpen(open);
          if (!open) {
            setCrashCopied(false);
            setBibtexCopied(false);
            setUpdateResult(null);
            setDiagnosticsError(null);
            setCodesignStatus(null);
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>About Kuro</DialogTitle>
            <DialogDescription>
              Kuro v{__APP_VERSION__}
              <br />
              SDM primer batch design tool with Tm-guided overlap extension.
              <br />
              <br />
              Built with Tauri + React + primer3-py
              <br />
              <br />
              <a
                href="https://github.com/gyuminlee-repo/KURO"
                target="_blank"
                rel="noopener noreferrer"
                className="text-info underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                github.com/gyuminlee-repo/KURO
              </a>
            </DialogDescription>
          </DialogHeader>

          {/* §9 Updates */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">Updates</p>
            <Button
              size="sm"
              variant="outline"
              disabled={updateChecking || updateInstalling}
              onClick={() => void handleCheckForUpdates()}
            >
              {updateChecking ? "Checking..." : "Check for updates"}
            </Button>
            {updateResult && (
              <div className="rounded-md border border-border px-3 py-2 text-xs">
                {updateResult.status === "up-to-date" && (
                  <p className="text-success">
                    You&apos;re on the latest version (v{updateResult.currentVersion}).
                  </p>
                )}
                {updateResult.status === "available" && (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-foreground">
                      Update available: v{__APP_VERSION__} → v{updateResult.newVersion}
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={updateInstalling}
                        onClick={() => void handleDownloadAndInstall(updateResult.update)}
                      >
                        {updateInstalling ? "Installing..." : "Download and Install"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setUpdateResult(null)}
                      >
                        Later
                      </Button>
                    </div>
                  </div>
                )}
                {updateResult.status === "not-configured" && (
                  <p className="text-warning">{updateResult.message}</p>
                )}
                {updateResult.status === "error" && (
                  <p className="text-destructive">Update check failed: {updateResult.message}</p>
                )}
              </div>
            )}
          </div>

          {/* How to cite */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">How to cite</p>
            <pre className="overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {KURO_BIBTEX}
            </pre>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void handleCopyBibtex()}
            >
              {bibtexCopied ? "Copied!" : "Copy BibTeX"}
            </Button>
          </div>

          {/* License */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">License</p>
            <p className="text-xs text-muted-foreground">
              Internal use, KRIBB C1 Lab — DOI/citation forthcoming
            </p>
          </div>

          {/* External services */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">External services</p>
            <ul className="text-xs text-muted-foreground space-y-0.5 list-none pl-0">
              <li>
                <span className="font-medium text-foreground">UniProt</span>
                {" ("}
                <a
                  href="https://www.uniprot.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  uniprot.org
                </a>
                {") — protein sequence search"}
              </li>
              <li>
                <span className="font-medium text-foreground">NCBI BLAST (EBI)</span>
                {" ("}
                <a
                  href="https://www.ebi.ac.uk"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  ebi.ac.uk
                </a>
                {") — sequence similarity search"}
              </li>
              <li>
                <span className="font-medium text-foreground">AlphaFold (EBI)</span>
                {" ("}
                <a
                  href="https://alphafold.ebi.ac.uk"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  alphafold.ebi.ac.uk
                </a>
                {") — structure prediction lookup"}
              </li>
              <li>
                <span className="font-medium text-foreground">InterPro / Pfam (EBI)</span>
                {" ("}
                <a
                  href="https://www.ebi.ac.uk/interpro"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  ebi.ac.uk/interpro
                </a>
                {") — protein domain annotation"}
              </li>
            </ul>
            <p className="text-xs text-muted-foreground">
              동의 상태:{" "}
              <span className={networkConsentGranted ? "text-success font-medium" : "text-warning font-medium"}>
                {networkConsentGranted ? "동의함" : "미동의"}
              </span>
            </p>
          </div>

          {/* §6 Language slot */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">Language</p>
            <div className="flex items-center gap-2">
              <LocaleToggle variant="icon-label" />
            </div>
            <p className="text-xs text-muted-foreground">
              현재는 슬롯만 제공됩니다. 향후 번역 도입 시 활성화됩니다.
            </p>
          </div>

          {/* Notifications */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">Notifications</p>
            <p className="text-xs text-muted-foreground">
              OS Notifications:{" "}
              <span className={notifyPermission ? "text-success font-medium" : "text-warning font-medium"}>
                {notifyPermission ? "enabled" : "disabled"}
              </span>
            </p>
            {!notifyPermission && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => void handleEnableNotifications()}
              >
                Enable Notifications
              </Button>
            )}
            <p className="text-xs text-muted-foreground">
              Fired for jobs lasting longer than 5 minutes.
            </p>
            <p className="text-xs text-muted-foreground">
              Sleep prevention: enabled while jobs run.
            </p>
          </div>

          {/* Offline mode toggle */}
          <div className="flex items-start gap-3 rounded-md border border-border px-3 py-2">
            <input
              id="kuro-offline-mode"
              type="checkbox"
              checked={offlineMode}
              onChange={(e) => setOfflineMode(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-primary"
              aria-label="오프라인 모드 토글"
            />
            <Label htmlFor="kuro-offline-mode" className="text-sm cursor-pointer">
              오프라인 모드
              <span className="block text-xs text-muted-foreground font-normal">
                켜면 모든 외부 서비스 호출이 차단됩니다
              </span>
            </Label>
          </div>

          {/* §20 Third-party licenses */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">Third-party licenses</p>
            {noticeLoading ? (
              <p className="text-xs text-muted-foreground">Loading...</p>
            ) : noticeText !== null ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setNoticeOpen(true)}
              >
                View licenses
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">
                Third-party licenses available in distribution package.
              </p>
            )}
          </div>

          {/* §11 Build & Distribution: Build SHA + Code Signing */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">Build</p>
            <p className="font-mono text-xs text-muted-foreground">
              SHA: {__BUILD_SHA__}
            </p>
            <p className="text-xs text-muted-foreground">
              Code Signing:{" "}
              <span className="font-mono">{codesignStatus ?? "loading..."}</span>
            </p>
          </div>

          <div className="flex flex-col gap-2 mt-1">
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopyCrashLog}
            >
              {crashCopied ? "Copied!" : "Copy Crash Log"}
            </Button>

            {/* §16 Local Diagnostics */}
            <div className="flex flex-col gap-1">
              <Button
                size="sm"
                variant="outline"
                disabled={diagnosticsGenerating}
                onClick={() => { void handleGenerateDiagnostics(); }}
              >
                {diagnosticsGenerating ? "Generating..." : "Generate Diagnostics"}
              </Button>
              {diagnosticsError && (
                <p className="text-xs text-destructive" role="alert">
                  {diagnosticsError}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Saves app version, crash log, and recent logs to a local JSON file. No data is sent externally.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button size="sm" onClick={() => setAboutOpen(false)}>
              OK
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* §12 Reproducibility: manifest re-run 확인 모달 */}
      <ReRunManifestDialog
        open={reRunManifest !== null}
        manifest={reRunManifest}
        verifyResult={reRunVerify}
        onClose={() => {
          setReRunManifest(null);
          setReRunVerify(null);
        }}
        onStatusMessage={(msg) => useAppStore.setState({ statusMessage: msg })}
      />

      {/* §12 Reproducibility: manifest diff 모달 */}
      <ManifestDiffDialog
        open={diffOpen}
        manifestA={diffManifestA}
        manifestB={diffManifestB}
        onClose={() => {
          setDiffOpen(false);
          setDiffManifestA(null);
          setDiffManifestB(null);
        }}
      />

      {/* §14 Schema migration confirmation modal */}
      <WorkspaceMigrateDialog
        state={migrateDialog}
        loading={migrateLoading}
        onCancel={() => {
          setMigrateDialog(MIGRATE_DIALOG_CLOSED);
          setMigratePending(null);
        }}
        onConfirm={async () => {
          if (!migratePending) return;
          setMigrateLoading(true);
          try {
            await executeMigrateAndLoad(
              migrateDialog.filePath,
              migratePending,
              migrateDialog.fromVersion,
              migrateDialog.toVersion,
            );
            setMigrateDialog(MIGRATE_DIALOG_CLOSED);
            setMigratePending(null);
          } catch (err) {
            useAppStore.setState({
              statusMessage: `Migration failed: ${err instanceof Error ? err.message : String(err)}`,
            });
          } finally {
            setMigrateLoading(false);
          }
        }}
      />

      {/* §20 Third-party licenses modal */}
      <Dialog open={noticeOpen} onOpenChange={setNoticeOpen}>
        <DialogContent className="max-w-2xl max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Third-Party Licenses</DialogTitle>
            <DialogDescription>
              Open-source components bundled with this application.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto">
            <pre className="text-xs whitespace-pre-wrap font-mono leading-relaxed p-2">
              {noticeText}
            </pre>
          </div>
          <DialogFooter>
            <Button size="sm" onClick={() => setNoticeOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
