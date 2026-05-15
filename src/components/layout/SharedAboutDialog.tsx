/**
 * SharedAboutDialog — consolidated About dialog for KURO and MAME.
 *
 * Renders shared scaffolding (version, updates, citation, license,
 * third-party licenses, crash log copy, Advanced collapsible with
 * build/codesign/sidecar/diagnostics) plus app-specific sections
 * branched on the `kind` prop:
 *   - "kuro": GitHub link in description, offline-mode toggle, external
 *             services list (UniProt/BLAST/AlphaFold/InterPro) with
 *             consent indicator, button-style shortcuts entry, plain
 *             crash log copy.
 *   - "mame": data folder section, inline shortcuts table, no external
 *             services, augmented crash log header (app/sidecar/OS).
 *
 * Lazy-load behavior preserved verbatim from the original MenuBar
 * implementations (NOTICE.md on dialog open, codesign + sidecar path
 * on Advanced expand, MAME data folder on dialog open).
 */

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { resolveResource } from "@tauri-apps/api/path";
import { invoke } from "@tauri-apps/api/core";
import type { Update } from "@tauri-apps/plugin-updater";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { checkForUpdates, downloadAndInstall, type UpdateCheckResult } from "../../lib/updater";
import { generateDiagnosticsBundle } from "../../lib/diagnostics";
import { revealInOSFolder } from "../../lib/openFolder";
import { getCrashLog } from "../../lib/crashLog";
import { getConfig } from "../../lib/project";
import { rpc } from "../../lib/ipc";
import { getShortcutsFor } from "../../lib/shortcuts";
import { useAppStore } from "../../store/appStore";

export type SharedAboutKind = "kuro" | "mame";

interface SharedAboutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind: SharedAboutKind;
  /** Optional: parent supplies a shortcuts dialog opener (kuro variant uses this). */
  onOpenShortcuts?: () => void;
}

const KURO_BIBTEX = `@software{kuro_TBD,
  title  = {KURO: Kernel for Upstream Recombination Oligodesign},
  author = {Lee, Gyu Min and Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

const MAME_BIBTEX = `@software{mame_TBD,
  title  = {MAME: Multi-round Activity & Mutation Engine},
  author = {Lee, Gyu Min and Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

export function SharedAboutDialog({
  open,
  onOpenChange,
  kind,
  onOpenShortcuts,
}: SharedAboutDialogProps) {
  const { t } = useTranslation();
  const offlineMode = useAppStore((s) => s.offlineMode);
  const setOfflineMode = useAppStore((s) => s.setOfflineMode);
  const networkConsentGranted = useAppStore((s) => s.networkConsentGranted);

  const [bibtexCopied, setBibtexCopied] = useState(false);
  const [crashCopied, setCrashCopied] = useState(false);
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeLoading, setNoticeLoading] = useState(false);

  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [updateInstalling, setUpdateInstalling] = useState(false);

  const [codesignStatus, setCodesignStatus] = useState<string | null>(null);
  const [sidecarPath, setSidecarPath] = useState<string | null>(null);
  const [dataFolder, setDataFolder] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  const bibtex = kind === "kuro" ? KURO_BIBTEX : MAME_BIBTEX;
  const mameShortcuts = kind === "mame" ? getShortcutsFor("mame") : [];

  // §20: Load NOTICE.md from Tauri resources when About dialog opens.
  useEffect(() => {
    if (!open || noticeText !== null) return;
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
  }, [open, noticeText]);

  // §11 Build & Distribution: load codesign status once when Advanced opens.
  useEffect(() => {
    if (!open || !advancedOpen || codesignStatus !== null) return;
    void invoke<string>("get_codesign_status")
      .then((s) => setCodesignStatus(s))
      .catch(() => setCodesignStatus("unknown"));
  }, [open, advancedOpen, codesignStatus]);

  // §6 Settings: load sidecar binary path once when Advanced opens.
  useEffect(() => {
    if (!open || !advancedOpen || sidecarPath !== null) return;
    void invoke<string>("get_sidecar_path", { kind })
      .then(setSidecarPath)
      .catch(() => setSidecarPath(`${kind}-sidecar (path unavailable)`));
  }, [open, advancedOpen, sidecarPath, kind]);

  // §6 Settings (MAME): load data folder path once when About opens.
  useEffect(() => {
    if (kind !== "mame") return;
    if (!open || dataFolder !== null) return;
    void getConfig()
      .then((cfg) => setDataFolder(cfg.projects_root))
      .catch(() => setDataFolder("unknown"));
  }, [kind, open, dataFolder]);

  function handleClose(nextOpen: boolean) {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setBibtexCopied(false);
      setCrashCopied(false);
      setUpdateResult(null);
      setDiagnosticsError(null);
      setCodesignStatus(null);
      setDataFolder(null);
      setAdvancedOpen(false);
    }
  }

  async function handleCopyBibtex() {
    await navigator.clipboard.writeText(bibtex);
    setBibtexCopied(true);
    setTimeout(() => setBibtexCopied(false), 2000);
  }

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

  async function handleGenerateDiagnostics() {
    setDiagnosticsGenerating(true);
    setDiagnosticsError(null);
    try {
      // KURO: defaults to kuro appStore log buffer.
      // MAME: no sidecar log buffer — pass empty array.
      const filePath =
        kind === "mame"
          ? await generateDiagnosticsBundle([])
          : await generateDiagnosticsBundle();
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
    const entries = log
      .map(
        (e) =>
          `[${e.timestamp}] ${e.component}: ${e.message}${e.stack ? "\n" + e.stack : ""}`,
      )
      .join("\n---\n");

    let text = entries;
    if (kind === "mame") {
      // §4 Error UX: include reproduction metadata header for MAME.
      let sidecarVersion = "unknown";
      try {
        const health = await rpc<{ sidecar_version: string }>("mame", "health", {});
        sidecarVersion = health.sidecar_version;
      } catch {
        // sidecar may be unavailable during crash reporting — ignore
      }
      const header = [
        "=== MAME Crash Report ===",
        `App version  : ${typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "unknown"}`,
        `Sidecar      : ${sidecarVersion}`,
        `OS           : ${navigator.userAgent}`,
        `Timestamp    : ${new Date().toISOString()}`,
        "",
        "--- Error entries ---",
      ].join("\n");
      text = `${header}\n${entries}`;
    }

    await navigator.clipboard.writeText(text);
    setCrashCopied(true);
    setTimeout(() => setCrashCopied(false), 2000);
  }

  const dialogTitle = kind === "kuro" ? t("about.title") : t("about.titleMame");
  const versionLabel =
    kind === "kuro" ? `Kuro v${__APP_VERSION__}` : `MAME v${__APP_VERSION__}`;
  const advancedId = `${kind}-about-advanced`;

  const dialogContentClass =
    kind === "kuro"
      ? "max-w-2xl max-h-[90vh] flex flex-col"
      : "max-w-lg max-h-[85vh] overflow-y-auto";

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className={dialogContentClass}>
          <DialogHeader>
            <DialogTitle>{dialogTitle}</DialogTitle>
            <DialogDescription>
              {versionLabel}
              <br />
              {kind === "kuro" ? t("about.kuroDescription") : t("about.mameTagline")}
              <br />
              {kind === "kuro" ? (
                <>
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
                </>
              ) : (
                <>
                  {t("about.mameSummary")}
                  <br />
                  {t("about.mameBuiltWith")}
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          {kind === "kuro" ? (
            <div className="flex-1 overflow-y-auto pr-1 -mr-1">
              {renderBody()}
            </div>
          ) : (
            renderBody()
          )}

          <DialogFooter>
            <Button size="sm" onClick={() => handleClose(false)}>
              {t("about.ok")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* §20 Third-party licenses modal */}
      <Dialog open={noticeOpen} onOpenChange={setNoticeOpen}>
        <DialogContent
          className={
            kind === "kuro"
              ? "max-w-2xl max-h-[90vh] flex flex-col"
              : "max-w-2xl max-h-[70vh] flex flex-col"
          }
        >
          <DialogHeader>
            <DialogTitle>{t("about.thirdPartyLicensesTitle")}</DialogTitle>
            <DialogDescription>{t("about.thirdPartyLicensesDesc")}</DialogDescription>
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

  function renderBody() {
    return (
      <>
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
                    {t("about.updateAvailable", {
                      current: __APP_VERSION__,
                      next: updateResult.newVersion,
                    })}
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      disabled={updateInstalling}
                      onClick={() => void handleDownloadAndInstall(updateResult.update)}
                    >
                      {updateInstalling
                        ? t("about.installing")
                        : t("about.downloadAndInstall")}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setUpdateResult(null)}>
                      {t("about.later")}
                    </Button>
                  </div>
                </div>
              )}
              {updateResult.status === "not-configured" && (
                <p className="text-warning">{updateResult.message}</p>
              )}
              {updateResult.status === "error" && (
                <p className="text-destructive">
                  {t("about.updateCheckFailed", { message: updateResult.message })}
                </p>
              )}
            </div>
          )}
        </div>

        {/* How to cite */}
        <div className="flex flex-col gap-1.5">
          <p className="text-sm font-semibold text-foreground">{t("about.howToCite")}</p>
          <pre className="max-w-full overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            {bibtex}
          </pre>
          <Button size="sm" variant="outline" onClick={() => void handleCopyBibtex()}>
            {bibtexCopied ? t("about.copied") : t("about.copyBibtex")}
          </Button>
        </div>

        {/* License */}
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-foreground">{t("about.license")}</p>
          <p className="text-xs text-muted-foreground">{t("about.licenseText")}</p>
        </div>

        {/* §8 A11y: Keyboard shortcuts — kuro uses button, mame uses inline table */}
        {kind === "kuro" ? (
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">
              {t("settings.keyboardShortcuts")}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                handleClose(false);
                onOpenShortcuts?.();
              }}
            >
              {t("shortcutsDialog.title")}
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">
              {t("settings.keyboardShortcuts")}
            </p>
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="py-0.5 pr-3 text-left font-semibold text-muted-foreground">
                    {t("settings.shortcutKeys")}
                  </th>
                  <th className="py-0.5 text-left font-semibold text-muted-foreground">
                    {t("settings.shortcutAction")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {mameShortcuts.map((s) => (
                  <tr key={s.keys} className="border-b border-border/40 last:border-0">
                    <td className="py-0.5 pr-3 font-mono text-foreground">{s.keys}</td>
                    <td className="py-0.5 text-muted-foreground">{s.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* KURO: Offline mode toggle */}
        {kind === "kuro" && (
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
        )}

        {/* MAME: Data folder */}
        {kind === "mame" && (
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">
              {t("settings.dataFolder")}
            </p>
            <p
              className="font-mono text-xs text-muted-foreground break-all"
              title={dataFolder ?? undefined}
            >
              {dataFolder ?? t("common.loading")}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                handleClose(false);
                window.dispatchEvent(new CustomEvent("kuma:show-onboarding"));
              }}
            >
              {t("settings.dataFolderChange")}
            </Button>
          </div>
        )}

        {/* §20 Third-party licenses */}
        <div className="flex flex-col gap-1">
          <p className="text-sm font-semibold text-foreground">
            {t("about.thirdPartyLicenses")}
          </p>
          {noticeLoading ? (
            <p className="text-xs text-muted-foreground">{t("about.licensesLoading")}</p>
          ) : noticeText !== null ? (
            <Button size="sm" variant="outline" onClick={() => setNoticeOpen(true)}>
              {t("about.viewLicenses")}
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              {t("about.licensesNotBundled")}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2 mt-1">
          <Button size="sm" variant="outline" onClick={() => void handleCopyCrashLog()}>
            {crashCopied ? t("about.copied") : t("about.copyCrashLog")}
          </Button>
        </div>

        {/* Advanced collapsible: External services, Build info, Diagnostics, Codesign */}
        <div className="border-t border-border pt-2">
          <button
            type="button"
            aria-expanded={advancedOpen}
            aria-controls={advancedId}
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
            <div id={advancedId} className="mt-3 flex flex-col gap-3">
              {/* External services */}
              <div className="flex flex-col gap-1.5">
                <p className="text-sm font-semibold text-foreground">
                  {t("about.externalServices")}
                </p>
                {kind === "kuro" ? (
                  <>
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
                        <span className="font-medium text-foreground">
                          InterPro / Pfam (EBI)
                        </span>
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
                      <span
                        className={
                          networkConsentGranted
                            ? "text-success font-medium"
                            : "text-warning font-medium"
                        }
                      >
                        {networkConsentGranted
                          ? t("menuBar.consentGranted")
                          : t("menuBar.consentNotGranted")}
                      </span>
                    </p>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {t("about.mameNoExternalServices")}
                  </p>
                )}
              </div>

              {/* §11 Build info + Codesign */}
              <div className="flex flex-col gap-1">
                <p className="text-sm font-semibold text-foreground">{t("about.build")}</p>
                <p className="font-mono text-xs text-muted-foreground">
                  SHA: {__BUILD_SHA__}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t("about.codesigning")}{" "}
                  <span className="font-mono">
                    {codesignStatus ?? t("common.loading")}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {t("about.sidecar")}{" "}
                  <span className="font-mono break-all">
                    {sidecarPath ?? t("common.loading")}
                  </span>
                </p>
              </div>

              {/* §16 Local Diagnostics */}
              <div className="flex flex-col gap-1">
                <p className="text-sm font-semibold text-foreground">
                  {t("about.diagnostics")}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={diagnosticsGenerating}
                  onClick={() => void handleGenerateDiagnostics()}
                >
                  {diagnosticsGenerating
                    ? t("about.generating")
                    : t("about.generateDiagnostics")}
                </Button>
                {diagnosticsError && (
                  <p className="text-xs text-destructive" role="alert">
                    {diagnosticsError}
                  </p>
                )}
                <p className="text-xs text-muted-foreground">{t("about.diagnosticsNote")}</p>
              </div>
            </div>
          )}
        </div>
      </>
    );
  }
}
