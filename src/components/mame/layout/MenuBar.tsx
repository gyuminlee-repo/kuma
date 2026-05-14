import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { resolveResource } from "@tauri-apps/api/path";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { CrashLogDialog } from "@/components/dialogs/CrashLogDialog";
import { RunReportDialog } from "@/components/mame/dialogs/RunReportDialog";
import { ReRunManifestDialog } from "@/components/dialogs/ReRunManifestDialog";
import { selectCanRun } from "@/store/mame/selectors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SubtoolMenuBar } from "@/components/layout/SubtoolMenuBar";
import { SettingsDialog } from "@/components/layout/SettingsDialog";
import { KeyboardShortcutsDialog } from "@/components/dialogs/KeyboardShortcutsDialog";
import { checkForUpdates, downloadAndInstall, type UpdateCheckResult } from "@/lib/updater";
import type { Update } from "@tauri-apps/plugin-updater";
import { invoke } from "@tauri-apps/api/core";
import { killSidecar, rpc } from "@/lib/ipc";
import { getConfig } from "@/lib/project";
import { getShortcutsFor } from "@/lib/shortcuts";
import { getCrashLog } from "@/lib/crashLog";
import { generateDiagnosticsBundle } from "@/lib/diagnostics";
import { revealInOSFolder } from "@/lib/openFolder";
import { useAppStore } from "@/store/appStore";
import { useTheme } from "@/components/ui/ThemeToggle";
import type { Theme } from "@/components/ui/ThemeToggle";
import i18next, { setLocale, SUPPORTED_LOCALES } from "@/lib/i18n";
import type { RunManifest } from "@/lib/runManifest";
import { loadManifestFromFile } from "@/lib/runManifest";
import type { InputVerifyResult } from "@/lib/reRun";

const MOD_KEY = typeof navigator !== "undefined" && navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

/** A: SidecarHealth — 모듈 스코프 (architect §responsive 필드 추가) */
interface SidecarHealth {
  alive: boolean;
  responsive: boolean;
  kind: string;
  pid: number | null;
  version: string | null;
  uptime_secs: number | null;
  message: string;
}

/** 메뉴 트리거 공통 클래스 (계획서 §6.1 권장) */
const TRIGGER_CLS =
  "h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors duration-fast text-caption font-medium text-foreground/80";

const LOCALE_NATIVE_NAMES: Record<typeof SUPPORTED_LOCALES[number], string> = {
  en: "English",
  ko: "한국어",
  "zh-CN": "中文(简体)",
  "zh-TW": "中文(繁體)",
  ja: "日本語",
  es: "Español",
  de: "Deutsch",
  fr: "Français",
  "pt-BR": "Português (BR)",
  ru: "Русский",
};

const THEME_ITEMS: { value: Theme; labelKey: string }[] = [
  { value: "light", labelKey: "menuBar.view.theme.light" },
  { value: "dark", labelKey: "menuBar.view.theme.dark" },
  { value: "system", labelKey: "menuBar.view.theme.system" },
];

interface MenuBarProps {
  onClearRequest: () => void;
  /** JANUS export dialog 열기 — MameAppLayout에서 janusOpen 상태 소유. */
  onJanusOpen?: () => void;
}

export function MenuBar({ onClearRequest, onJanusOpen }: MenuBarProps) {
  const { t } = useTranslation();
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const runAnalysis = useMameAppStore((s) => s.runAnalysis);
  const validateInputs = useMameAppStore((s) => s.validateInputs);
  const openExport = useMameAppStore((s) => s.openExport);
  const cancelAnalysis = useMameAppStore((s) => s.cancelAnalysis);
  const loadSampleData = useMameAppStore((s) => s.loadSampleData);
  const canRun = useMameAppStore(selectCanRun);
  const logPanelVisible = useAppStore((s) => s.logPanelVisible);
  const toggleLogPanel = useAppStore((s) => s.toggleLogPanel);
  const jobsPanelVisible = useAppStore((s) => s.jobsPanelVisible);
  const toggleJobsPanel = useAppStore((s) => s.toggleJobsPanel);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [bibtexCopied, setBibtexCopied] = useState(false);
  const [crashLogOpen, setCrashLogOpen] = useState(false);
  const [crashCopied, setCrashCopied] = useState(false);
  // §20 Citation & Licensing: NOTICE.md from bundled resources
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [noticeLoading, setNoticeLoading] = useState(false);

  // §9 Versioning & Updates
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateResult, setUpdateResult] = useState<UpdateCheckResult | null>(null);
  const [updateInstalling, setUpdateInstalling] = useState(false);

  // §11 Build & Distribution: codesign status (lazy-loaded when About opens)
  const [codesignStatus, setCodesignStatus] = useState<string | null>(null);

  // §6 Settings: data folder path (lazy-loaded when About opens)
  const [dataFolder, setDataFolder] = useState<string | null>(null);
  // §6 Settings: sidecar binary path (lazy-loaded when About opens)
  const [sidecarPath, setSidecarPath] = useState<string | null>(null);

  // D-7: Advanced collapsible state
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // §8 A11y: keyboard shortcuts table data
  const mameShortcuts = getShortcutsFor("mame");

  const MAME_BIBTEX = `@software{mame_TBD,
  title  = {MAME: Multi-round Activity & Mutation Engine},
  author = {Lee, Gyu Min and Kang, Hyemin and KRIBB C1 Lab},
  year   = {2026},
  note   = {DOI/citation forthcoming},
  url    = {TBD}
}`;

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

  // §11 Build & Distribution: load codesign status once when Advanced section opens
  useEffect(() => {
    if (!aboutOpen || !advancedOpen || codesignStatus !== null) return;
    void invoke<string>("get_codesign_status")
      .then((s) => setCodesignStatus(s))
      .catch(() => setCodesignStatus("unknown"));
  }, [aboutOpen, advancedOpen, codesignStatus]);

  // §6 Settings: load data folder path once when About opens
  useEffect(() => {
    if (!aboutOpen || dataFolder !== null) return;
    void getConfig()
      .then((cfg) => setDataFolder(cfg.projects_root))
      .catch(() => setDataFolder("unknown"));
  }, [aboutOpen, dataFolder]);

  // §6 Settings: load sidecar binary path once when Advanced section opens
  useEffect(() => {
    if (!aboutOpen || !advancedOpen || sidecarPath !== null) return;
    void invoke<string>("get_sidecar_path", { kind: "mame" })
      .then(setSidecarPath)
      .catch(() => setSidecarPath("mame-sidecar (path unavailable)"));
  }, [aboutOpen, advancedOpen, sidecarPath]);

  // 2-A: Preferences / Shortcuts dialogs
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  // 2-B: Manifest re-run state
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);
  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);

  // Theme hook (2-D)
  const { theme, setTheme } = useTheme();

  // §D3.5: View 메뉴 단축키 (Ctrl/Cmd+L: Logs, Ctrl/Cmd+J: Jobs)
  // + 2-A: Ctrl+, Preferences, Ctrl+/ Shortcuts
  const handleViewKeyDown = useCallback((e: KeyboardEvent) => {
    // B: input/textarea/contenteditable 포커스 시 전역 단축키 무시
    const target = e.target as HTMLElement;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
    // F11: fullscreen toggle (modifier 없음) — C: .catch 추가
    if (e.key === "F11") {
      e.preventDefault();
      void getCurrentWindow().isFullscreen().then((full) =>
        getCurrentWindow().setFullscreen(!full)
      ).catch((err: unknown) =>
        toast.error(t("menuBar.view.fullscreenError", { message: err instanceof Error ? err.message : String(err) }))
      );
      return;
    }
    if (!(e.metaKey || e.ctrlKey)) return;
    switch (e.key.toLowerCase()) {
      case "l":
        e.preventDefault();
        toggleLogPanel();
        break;
      case "j":
        e.preventDefault();
        toggleJobsPanel();
        break;
      case ",":
        e.preventDefault();
        setPreferencesOpen((v) => !v);
        break;
      case "/":
        e.preventDefault();
        setShortcutsOpen((v) => !v);
        break;
    }
  }, [toggleLogPanel, toggleJobsPanel]);

  useEffect(() => {
    window.addEventListener("keydown", handleViewKeyDown);
    return () => window.removeEventListener("keydown", handleViewKeyDown);
  }, [handleViewKeyDown]);

  // 2-B: Replay saved run — D: openDialog 자체 실패도 catch
  async function handleMameReplay() {
    try {
      const selected = await openDialog({
        filters: [{ name: "Manifest", extensions: ["json"] }],
      });
      if (!selected) return;
      const path = typeof selected === "string" ? selected : selected[0];
      if (!path) return;
      try {
        const manifest = await loadManifestFromFile(path);
        setReRunManifest(manifest);
      } catch (err) {
        toast.error(t("menuBar.run.replayError", { message: err instanceof Error ? err.message : String(err) }));
      }
    } catch (err) {
      toast.error(t("menuBar.run.replayError", { message: err instanceof Error ? err.message : String(err) }));
    }
  }

  // 2-B: Check sidecar health — A: interface 모듈 스코프 이동 완료, 토스트 3-way 분기
  async function handleCheckMameSidecarHealth() {
    try {
      const health = await invoke<SidecarHealth>("check_sidecar_health", { kind: "mame" });
      if (health.alive && health.responsive) {
        toast.success(t("menuBar.run.sidecarHealthAlive", { version: health.version ?? "unknown", uptime: health.uptime_secs ?? 0 }));
      } else if (health.alive && !health.responsive) {
        toast.warning(t("menuBar.run.sidecarHealthUnresponsive", { message: health.message }));
      } else {
        toast.warning(t("menuBar.run.sidecarHealthDead"));
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  }

  // §4 Error UX: copy repro info (app version + OS + sidecar version + last RPC error trace)
  async function handleCopyCrashLog() {
    const log = getCrashLog();
    if (log.length === 0) {
      setCrashCopied(false);
      return;
    }

    // Collect sidecar version (best-effort; fallback to "unknown" on error)
    let sidecarVersion = "unknown";
    try {
      const health = await rpc<{ sidecar_version: string }>("mame", "health", {});
      sidecarVersion = health.sidecar_version;
    } catch {
      // sidecar may be unavailable during crash reporting — ignore
    }

    // Build header with reproduction metadata
    const header = [
      "=== MAME Crash Report ===",
      `App version  : ${typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "unknown"}`,
      `Sidecar      : ${sidecarVersion}`,
      `OS           : ${navigator.userAgent}`,
      `Timestamp    : ${new Date().toISOString()}`,
      "",
      "--- Error entries ---",
    ].join("\n");

    const entries = log
      .map(
        (e) =>
          `[${e.timestamp}] ${e.component}: ${e.message}${e.stack ? "\n" + e.stack : ""}`,
      )
      .join("\n---\n");

    await navigator.clipboard.writeText(`${header}\n${entries}`);
    setCrashCopied(true);
    setTimeout(() => setCrashCopied(false), 2000);
  }

  async function handleCopyBibtex() {
    await navigator.clipboard.writeText(MAME_BIBTEX);
    setBibtexCopied(true);
    setTimeout(() => setBibtexCopied(false), 2000);
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

  // §16 Diagnostics
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

  async function handleGenerateDiagnostics() {
    setDiagnosticsGenerating(true);
    setDiagnosticsError(null);
    try {
      // mame has no sidecar log buffer — pass empty array
      const filePath = await generateDiagnosticsBundle([]);
      if (filePath) {
        await revealInOSFolder(filePath);
      }
    } catch (err) {
      setDiagnosticsError(err instanceof Error ? err.message : String(err));
    } finally {
      setDiagnosticsGenerating(false);
    }
  }

  const [runReportOpen, setRunReportOpen] = useState(false);

  // JANUS dialog는 MameAppLayout이 단독 소유. MenuBar는 prop 콜백만 호출.
  const openJanus = () => {
    onJanusOpen?.();
  };

  const menus = (
    <>
      {/* App 메뉴 — mockup v5: 첫 메뉴는 앱명(mame), 굵게. MAME 탭에서는 "mame"만 노출. */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={`${TRIGGER_CLS} font-bold`}>{t("menuBar.appMenu.mame")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem
            onClick={() => window.dispatchEvent(new CustomEvent("kuma:return-to-home"))}
          >
            <span className="flex-1">{t("file.openProject")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void validateInputs()} disabled={isAnalyzing}>
            <span className="flex-1">{t("file.validateInputs")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void runAnalysis()} disabled={!canRun}>
            <span className="flex-1">{t("file.runAnalysis")}</span>
            <DropdownMenuShortcut>{MOD_KEY}D</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void cancelAnalysis()} disabled={!isAnalyzing}>
            <span className="flex-1">{t("file.cancelAnalysis")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {/* §1 Recovery: UI 상태 보존 sidecar 재시작. Zustand 스토어는 메모리에 유지됨 */}
          <DropdownMenuItem
            onClick={() => {
              if (isAnalyzing && !window.confirm(t("mame.menuBar.restartSidecarConfirm"))) return;
              void killSidecar("mame");
            }}
            disabled={false}
          >
            {t("file.restartSidecar")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={openExport} disabled={!hasResults}>
            <span className="flex-1">{t("export.excel")}</span>
            <DropdownMenuShortcut>{MOD_KEY}E</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={openJanus} disabled={!hasResults}>
            <span className="flex-1">{t("export.janusMapping")}</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setRunReportOpen(true)} disabled={!hasResults}>
            <span className="flex-1">{t("export.runReport")}</span>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => { void getCurrentWindow().close(); }}>
            <span className="flex-1">{t("menuBar.appMenu.closeWindow")}</span>
            <DropdownMenuShortcut>{MOD_KEY}W</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => { void getCurrentWindow().destroy(); }}>
            <span className="flex-1">{t("menuBar.appMenu.quit")}</span>
            <DropdownMenuShortcut>{MOD_KEY}Q</DropdownMenuShortcut>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Edit 메뉴 — 2-A: Preferences 추가 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menu.edit")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={onClearRequest} disabled={!hasResults || isAnalyzing}>
            {t("edit.clearResults")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setPreferencesOpen(true)}>
            <span className="flex-1">{t("menuBar.edit.preferences")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY},</kbd>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* View 메뉴 — 2-D: Language/Theme/Fullscreen 서브메뉴 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menuBar.view.title")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={toggleLogPanel}>
            <span className="flex-1">
              {logPanelVisible ? "✓ " : ""}{t("menuBar.view.logs")}
            </span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}L</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={toggleJobsPanel}>
            <span className="flex-1">
              {jobsPanelVisible ? "✓ " : ""}{t("menuBar.view.jobs")}
            </span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}J</kbd>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{t("menuBar.view.language")}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {SUPPORTED_LOCALES.map((code) => (
                <DropdownMenuItem
                  key={code}
                  onClick={() => {
                    setLocale(code);
                  }}
                  aria-current={i18next.language === code ? "true" : undefined}
                >
                  <span className="flex-1">
                    {i18next.language === code ? "✓ " : ""}
                    {LOCALE_NATIVE_NAMES[code]}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{t("menuBar.view.theme.title")}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {THEME_ITEMS.map(({ value, labelKey }) => (
                <DropdownMenuItem
                  key={value}
                  onClick={() => setTheme(value)}
                  aria-current={theme === value ? "true" : undefined}
                >
                  <span className="flex-1">
                    {theme === value ? "✓ " : ""}
                    {t(labelKey)}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => {
              void getCurrentWindow().isFullscreen().then((full) =>
                getCurrentWindow().setFullscreen(!full)
              );
            }}
          >
            <span className="flex-1">{t("menuBar.view.fullscreen")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">F11</kbd>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Run 메뉴 신설 — 2-B */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menuBar.run.title")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem
            onClick={() => { void handleGenerateDiagnostics(); }}
            disabled={diagnosticsGenerating}
          >
            {diagnosticsGenerating ? t("about.generating") : t("menuBar.run.diagnostics")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => { void handleMameReplay(); }}>
            {t("menuBar.run.replay")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => { void handleCheckMameSidecarHealth(); }}>
            {t("menuBar.run.checkSidecar")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Help 메뉴 — 2-C: Shortcuts / Report issue / Check updates 추가 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menu.help")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={loadSampleData} disabled={isAnalyzing}>
            {t("help.loadSampleData")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => window.dispatchEvent(new CustomEvent("kuma:show-onboarding"))}>
            {t("help.showOnboarding")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setShortcutsOpen(true)}>
            <span className="flex-1">{t("shortcutsDialog.title")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}/</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setCrashLogOpen(true)}>
            {t("help.viewCrashLog")}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => { void handleCheckForUpdates(); setAboutOpen(true); }}
            disabled={updateChecking}
          >
            {t("about.checkForUpdates")}
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => {
              void import("@tauri-apps/plugin-shell").then((m) =>
                m.open("https://github.com/gyuminlee-repo/KURO/issues"),
              );
            }}
          >
            {t("menuBar.help.reportIssue")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>{t("about.titleMame")}</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <CrashLogDialog open={crashLogOpen} onOpenChange={setCrashLogOpen} />
      <RunReportDialog open={runReportOpen} onOpenChange={setRunReportOpen} />

      <SettingsDialog open={preferencesOpen} onOpenChange={setPreferencesOpen} scope="mame" />
      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} scope="mame" />

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

      <SubtoolMenuBar
        label="Mame"
        subtitle={t("about.mameTagline")}
        menus={menus}
      />

      <Dialog
        open={aboutOpen}
        onOpenChange={(open: boolean) => {
          setAboutOpen(open);
          if (!open) {
            setBibtexCopied(false);
            setUpdateResult(null);
            setCodesignStatus(null);
            setDataFolder(null);
            setDiagnosticsError(null);
            setAdvancedOpen(false);
          }
        }}
      >
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("about.titleMame")}</DialogTitle>
            <DialogDescription>
              MAME v{__APP_VERSION__}
              <br />
              {t("about.mameTagline")}
              <br />
              {t("about.mameSummary")}
              <br />
              {t("about.mameBuiltWith")}
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
              {MAME_BIBTEX}
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
                {mameShortcuts.map((s) => (
                  <tr key={s.keys} className="border-b border-border/40 last:border-0">
                    <td className="py-0.5 pr-3 font-mono text-foreground">{s.keys}</td>
                    <td className="py-0.5 text-muted-foreground">{s.action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* §6 Settings: Data folder */}
          <div className="flex flex-col gap-1.5">
            <p className="text-sm font-semibold text-foreground">{t("settings.dataFolder")}</p>
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
                setAboutOpen(false);
                window.dispatchEvent(new CustomEvent("kuma:show-onboarding"));
              }}
            >
              {t("settings.dataFolderChange")}
            </Button>
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
              onClick={() => { void handleCopyCrashLog(); }}
            >
              {crashCopied ? t("about.copied") : t("about.copyCrashLog")}
            </Button>
          </div>

          {/* Advanced collapsible: External services, Build info, Diagnostics, Codesign */}
          <div className="border-t border-border pt-2">
            <button
              type="button"
              aria-expanded={advancedOpen}
              aria-controls="mame-about-advanced"
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
              <div id="mame-about-advanced" className="mt-3 flex flex-col gap-3">
                {/* External services */}
                <div className="flex flex-col gap-1.5">
                  <p className="text-sm font-semibold text-foreground">{t("about.externalServices")}</p>
                  <p className="text-xs text-muted-foreground">
                    {t("about.mameNoExternalServices")}
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
                <div className="flex flex-col gap-1.5">
                  <p className="text-sm font-semibold text-foreground">{t("about.diagnostics")}</p>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={diagnosticsGenerating}
                    onClick={() => void handleGenerateDiagnostics()}
                  >
                    {diagnosticsGenerating ? t("about.generating") : t("about.generateDiagnostics")}
                  </Button>
                  {diagnosticsError && (
                    <p className="text-xs text-destructive">{diagnosticsError}</p>
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
