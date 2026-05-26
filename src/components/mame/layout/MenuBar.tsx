import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { CrashLogDialog } from "@/components/dialogs/CrashLogDialog";
import { RunReportDialog } from "@/components/mame/dialogs/RunReportDialog";
import { ReRunManifestDialog } from "@/components/dialogs/ReRunManifestDialog";
import { selectCanRun } from "@/store/mame/selectors";
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
import { SharedAboutDialog } from "@/components/layout/SharedAboutDialog";
import { invoke } from "@tauri-apps/api/core";
import { killSidecar } from "@/lib/ipc";
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
  onRunRequest: () => void;
  /** JANUS export dialog 열기 — MameAppLayout에서 janusOpen 상태 소유. */
  onJanusOpen?: () => void;
}

export function MenuBar({ onClearRequest, onRunRequest, onJanusOpen }: MenuBarProps) {
  const { t } = useTranslation();
  const hasResults = useMameAppStore((s) => s.verdicts.length > 0);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
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
  const [crashLogOpen, setCrashLogOpen] = useState(false);

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

  // §16 Diagnostics
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState(false);

  async function handleGenerateDiagnostics() {
    setDiagnosticsGenerating(true);
    try {
      // mame has no sidecar log buffer — pass empty array
      const filePath = await generateDiagnosticsBundle([]);
      if (filePath) {
        await revealInOSFolder(filePath);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
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
          <DropdownMenuItem onClick={onRunRequest} disabled={!canRun}>
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
            {t("appLayout.clearAll")}
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
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
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

      <SharedAboutDialog
        open={aboutOpen}
        onOpenChange={setAboutOpen}
        kind="mame"
      />


    </>
  );
}
