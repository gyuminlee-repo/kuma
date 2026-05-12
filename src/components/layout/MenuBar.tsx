import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../store/appStore";
import { generateDiagnosticsBundle } from "../../lib/diagnostics";
import { revealInOSFolder } from "../../lib/openFolder";
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
  handleOpenSequence,
  executeMigrateAndLoad,
  MIGRATE_DIALOG_CLOSED,
} from "./export-handlers";
import { WorkspaceMigrateDialog } from "../dialogs/WorkspaceMigrateDialog";
import type { MigrateDialogState } from "../dialogs/WorkspaceMigrateDialog";
import { SubtoolMenuBar } from "./SubtoolMenuBar";
import type { RunManifest } from "../../lib/runManifest";
import type { InputVerifyResult } from "../../lib/reRun";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { resolveResource } from "@tauri-apps/api/path";
import { ReRunManifestDialog } from "../dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "../dialogs/ManifestDiffDialog";
import { checkForUpdates, downloadAndInstall, type UpdateCheckResult } from "../../lib/updater";
import type { Update } from "@tauri-apps/plugin-updater";
import { invoke } from "@tauri-apps/api/core";
import { killSidecar } from "../../lib/ipc";
import { getShortcutsFor } from "../../lib/shortcuts";

const MOD_KEY = navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

/** 메뉴 트리거 공통 클래스 (계획서 §6.1 권장) */
const TRIGGER_CLS =
  "h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast text-caption font-medium text-foreground/80";

export function MenuBar() {
  const { t } = useTranslation();
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
  // §20 Citation & Licensing: NOTICE.md from bundled resources
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeLoading, setNoticeLoading] = useState(false);

  // §12 Reproducibility: manifest 파일 picker
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);

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

  // §8 A11y: keyboard shortcuts table data
  const kuroShortcuts = getShortcutsFor("kuro");

  // §6 Settings: sidecar binary path (lazy-loaded when About opens)
  const [sidecarPath, setSidecarPath] = useState<string | null>(null);

  // D-5: Advanced collapsible state
  const [advancedOpen, setAdvancedOpen] = useState(false);



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

  // §11 Build & Distribution: load codesign status once when About opens (advanced section)
  useEffect(() => {
    if (!aboutOpen || !advancedOpen || codesignStatus !== null) return;
    void invoke<string>("get_codesign_status")
      .then((s) => setCodesignStatus(s))
      .catch(() => setCodesignStatus("unknown"));
  }, [aboutOpen, advancedOpen, codesignStatus]);

  // §6 Settings: load sidecar binary path once when About opens (advanced section)
  useEffect(() => {
    if (!aboutOpen || !advancedOpen || sidecarPath !== null) return;
    void invoke<string>("get_sidecar_path", { kind: "kuro" })
      .then(setSidecarPath)
      .catch(() => setSidecarPath("kuro-sidecar (path unavailable)"));
  }, [aboutOpen, advancedOpen, sidecarPath]);

  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);

  // §14 Migration dialog state
  const [migrateDialog, setMigrateDialog] = useState<MigrateDialogState>(MIGRATE_DIALOG_CLOSED);
  const [migratePending, setMigratePending] = useState<Record<string, unknown> | null>(null);
  const [migrateLoading, setMigrateLoading] = useState(false);

  const KURO_BIBTEX = `@software{kuro_TBD,
  title  = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Lee, Gyu Min and Kang, Hyemin and KRIBB C1 Lab},
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
          <button className={TRIGGER_CLS}>{t("menuBar.fileMenuTrigger")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={handleOpenSequence}>
            <span className="flex-1">{t("file.openSequence")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}O</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => window.dispatchEvent(new CustomEvent("kuma:return-to-home"))}
          >
            {t("file.openProject")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {/* §1 Recovery: UI 상태 보존 sidecar 재시작. Zustand 스토어는 메모리에 유지됨 */}
          <DropdownMenuItem
            onClick={() => {
              const busy = isDesigning || isExporting;
              if (busy && !window.confirm(t("menuBar.restartSidecarBusyConfirm"))) return;
              void killSidecar("kuro");
            }}
            disabled={false}
          >
            {t("file.restartSidecar")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Help 메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menu.help")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={loadSampleData}>
            {t("help.loadSampleData")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => window.dispatchEvent(new CustomEvent("kuma:show-onboarding"))}>
            {t("help.showOnboarding")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setCrashLogOpen(true)}>
            {t("help.viewCrashLog")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
            {t("about.titleKuro")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <SubtoolMenuBar
        label="Kuro"
        subtitle={t("menuBar.kuroSubtitle")}
        menus={menus}
      />

      <CrashLogDialog open={crashLogOpen} onOpenChange={setCrashLogOpen} />

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
            setAdvancedOpen(false);
          }
        }}
      >
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("about.title")}</DialogTitle>
            <DialogDescription>
              Kuro v{__APP_VERSION__}
              <br />
              {t("about.kuroDescription")}
              <br />
              <br />
              {t("about.kuroBuiltWith")}
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
            <p className="text-sm font-semibold text-foreground">{t("about.updates")}</p>
            <Button
              size="sm"
              variant="outline"
              disabled={updateChecking || updateInstalling}
              onClick={() => void handleCheckForUpdates()}
            >
              {updateChecking ? t("about.checking") : t("about.checkForUpdates")}
            </Button>
            {updateResult && (
              <div className="rounded-md border border-border px-3 py-2 text-xs">
                {updateResult.status === "up-to-date" && (
                  <p className="text-success">
                    {t("about.upToDate", { version: updateResult.currentVersion })}
                  </p>
                )}
                {updateResult.status === "available" && (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-foreground">
                      {t("about.updateAvailable", { current: __APP_VERSION__, next: updateResult.newVersion })}
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={updateInstalling}
                        onClick={() => void handleDownloadAndInstall(updateResult.update)}
                      >
                        {updateInstalling ? t("about.installing") : t("about.downloadAndInstall")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setUpdateResult(null)}
                      >
                        {t("about.later")}
                      </Button>
                    </div>
                  </div>
                )}
                {updateResult.status === "not-configured" && (
                  <p className="text-warning">{updateResult.message}</p>
                )}
                {updateResult.status === "error" && (
                  <p className="text-destructive">{t("about.updateCheckFailed", { message: updateResult.message })}</p>
                )}
              </div>
            )}
          </div>

          {/* How to cite */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">{t("about.howToCite")}</p>
            <pre className="max-w-full overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {KURO_BIBTEX}
            </pre>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void handleCopyBibtex()}
            >
              {bibtexCopied ? t("about.copied") : t("about.copyBibtex")}
            </Button>
          </div>

          {/* License */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">{t("about.license")}</p>
            <p className="text-xs text-muted-foreground">
              {t("about.licenseText")}
            </p>
          </div>

          {/* §8 A11y: Keyboard shortcuts table */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">{t("settings.keyboardShortcuts")}</p>
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-0.5 pr-3 text-left font-semibold text-muted-foreground">{t("settings.shortcutKeys")}</th>
                  <th className="py-0.5 text-left font-semibold text-muted-foreground">{t("settings.shortcutAction")}</th>
                </tr>
              </thead>
              <tbody>
                {kuroShortcuts.map((s) => (
                  <tr key={s.keys} className="border-b border-border/40 last:border-0">
                    <td className="py-0.5 pr-3 font-mono text-foreground">{s.keys}</td>
                    <td className="py-0.5 text-muted-foreground">{s.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Offline mode toggle */}
          <div className="flex items-start gap-3 rounded-md border border-border px-3 py-2">
            <input
              id="kuro-offline-mode"
              type="checkbox"
              checked={offlineMode}
              onChange={(e) => setOfflineMode(e.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-primary"
              aria-label={t("menuBar.offlineModeToggleAria")}
            />
            <label htmlFor="kuro-offline-mode" className="text-sm cursor-pointer">
              {t("menuBar.offlineModeLabel")}
              <span className="block text-xs text-muted-foreground font-normal">
                {t("menuBar.offlineModeDesc")}
              </span>
            </label>
          </div>

          {/* §20 Third-party licenses */}
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold text-foreground">{t("about.thirdPartyLicenses")}</p>
            {noticeLoading ? (
              <p className="text-xs text-muted-foreground">{t("about.licensesLoading")}</p>
            ) : noticeText !== null ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setNoticeOpen(true)}
              >
                {t("about.viewLicenses")}
              </Button>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("about.licensesNotBundled")}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2 mt-1">
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopyCrashLog}
            >
              {crashCopied ? t("about.copied") : t("about.copyCrashLog")}
            </Button>
          </div>

          {/* Advanced collapsible: External services, Build info, Diagnostics, Codesign */}
          <div className="border-t border-border pt-2">
            <button
              type="button"
              aria-expanded={advancedOpen}
              aria-controls="kuro-about-advanced"
              onClick={() => setAdvancedOpen((v) => !v)}
              className="flex w-full items-center gap-1.5 text-sm font-semibold text-foreground hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`shrink-0 transition-transform ${advancedOpen ? "rotate-90" : ""}`}
                aria-hidden="true"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
              {t("about.advanced")}
            </button>
            {advancedOpen && (
              <div id="kuro-about-advanced" className="mt-3 flex flex-col gap-3">
                {/* External services */}
                <div className="flex flex-col gap-1.5">
                  <p className="text-sm font-semibold text-foreground">{t("about.externalServices")}</p>
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
                      {t("menuBar.uniprotServiceSuffix")}
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
                      {t("menuBar.ncbiBlastServiceSuffix")}
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
                      {t("menuBar.alphafoldServiceSuffix")}
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
                      {t("menuBar.interproServiceSuffix")}
                    </li>
                  </ul>
                  <p className="text-xs text-muted-foreground">
                    {t("menuBar.consentStatusLabel")}{" "}
                    <span className={networkConsentGranted ? "text-success font-medium" : "text-warning font-medium"}>
                      {networkConsentGranted ? t("menuBar.consentGranted") : t("menuBar.consentNotGranted")}
                    </span>
                  </p>
                </div>

                {/* §11 Build info + Codesign */}
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-semibold text-foreground">{t("about.build")}</p>
                  <p className="font-mono text-xs text-muted-foreground">
                    SHA: {__BUILD_SHA__}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("about.codesigning")}{" "}
                    <span className="font-mono">{codesignStatus ?? t("common.loading")}</span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t("about.sidecar")}{" "}
                    <span className="font-mono break-all">{sidecarPath ?? t("common.loading")}</span>
                  </p>
                </div>

                {/* §16 Local Diagnostics */}
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-semibold text-foreground">{t("about.diagnostics")}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={diagnosticsGenerating}
                    onClick={() => { void handleGenerateDiagnostics(); }}
                  >
                    {diagnosticsGenerating ? t("about.generating") : t("about.generateDiagnostics")}
                  </Button>
                  {diagnosticsError && (
                    <p className="text-xs text-destructive" role="alert">
                      {diagnosticsError}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    {t("about.diagnosticsNote")}
                  </p>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button size="sm" onClick={() => setAboutOpen(false)}>
              {t("about.ok")}
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
            <DialogTitle>{t("about.thirdPartyLicensesTitle")}</DialogTitle>
            <DialogDescription>
              {t("about.thirdPartyLicensesDesc")}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto">
            <pre className="text-xs whitespace-pre-wrap font-mono leading-relaxed p-2">
              {noticeText}
            </pre>
          </div>
          <DialogFooter>
            <Button size="sm" onClick={() => setNoticeOpen(false)}>
              {t("common.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </>
  );
}
