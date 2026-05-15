import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAppStore } from "../../store/appStore";
import { generateDiagnosticsBundle } from "../../lib/diagnostics";
import { revealInOSFolder } from "../../lib/openFolder";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from "../ui/dropdown-menu";
import { useTheme } from "../ui/ThemeToggle";
import type { Theme } from "../ui/ThemeToggle";
import i18next, { setLocale, SUPPORTED_LOCALES } from "../../lib/i18n";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { loadManifestFromFile } from "../../lib/runManifest";
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
import { ReRunManifestDialog } from "../dialogs/ReRunManifestDialog";
import { ManifestDiffDialog } from "../dialogs/ManifestDiffDialog";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { killSidecar } from "../../lib/ipc";
import { SettingsDialog } from "./SettingsDialog";
import { KeyboardShortcutsDialog } from "../dialogs/KeyboardShortcutsDialog";
import { SharedAboutDialog } from "./SharedAboutDialog";

const MOD_KEY = navigator.userAgent.includes("Mac") ? "⌘" : "Ctrl+";

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

export function MenuBar() {
  const { t } = useTranslation();
  const isExporting = useAppStore((s) => s.isExporting);
  const isDesigning = useAppStore((s) => s.isDesigning);
  const loadSampleData = useAppStore((s) => s.loadSampleData);
  const offlineMode = useAppStore((s) => s.offlineMode);
  const setOfflineMode = useAppStore((s) => s.setOfflineMode);
  const networkConsentGranted = useAppStore((s) => s.networkConsentGranted);
  const logPanelVisible = useAppStore((s) => s.logPanelVisible);
  const toggleLogPanel = useAppStore((s) => s.toggleLogPanel);
  const jobsPanelVisible = useAppStore((s) => s.jobsPanelVisible);
  const toggleJobsPanel = useAppStore((s) => s.toggleJobsPanel);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [diagnosticsGenerating, setDiagnosticsGenerating] = useState(false);
  const [crashLogOpen, setCrashLogOpen] = useState(false);

  // §12 Reproducibility: manifest 파일 picker
  const [reRunManifest, setReRunManifest] = useState<RunManifest | null>(null);

  // §12 Reproducibility: manifest diff 모달 상태
  const [diffManifestA, setDiffManifestA] = useState<RunManifest | null>(null);
  const [diffManifestB, setDiffManifestB] = useState<RunManifest | null>(null);
  const [diffOpen, setDiffOpen] = useState(false);

  // Preferences / Keyboard shortcuts dialogs
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const [reRunVerify, setReRunVerify] = useState<InputVerifyResult | null>(null);

  // §D3.5: View 메뉴 단축키 (Ctrl/Cmd+L: Logs, Ctrl/Cmd+J: Jobs)
  // + Edit/Help 단축키 (Ctrl/Cmd+, Preferences, Ctrl/Cmd+/ Shortcuts)
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
    switch (e.key) {
      case "l":
      case "L":
        e.preventDefault();
        toggleLogPanel();
        return;
      case "j":
      case "J":
        e.preventDefault();
        toggleJobsPanel();
        return;
      case ",":
        e.preventDefault();
        setPreferencesOpen((v) => !v);
        return;
      case "/":
        e.preventDefault();
        setShortcutsOpen((v) => !v);
        return;
    }
  }, [toggleLogPanel, toggleJobsPanel]);

  useEffect(() => {
    window.addEventListener("keydown", handleViewKeyDown);
    return () => window.removeEventListener("keydown", handleViewKeyDown);
  }, [handleViewKeyDown]);

  // §12 Reproducibility: manifest 파일 picker (1-A) — D: openDialog 자체 실패도 catch
  async function handleReplay() {
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

  // §1-B: Check sidecar health — A: interface 모듈 스코프 이동 완료, 토스트 3-way 분기
  async function handleCheckSidecarHealth() {
    try {
      const health = await invoke<SidecarHealth>("check_sidecar_health", { kind: "kuro" });
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

  // Theme hook (1-D)
  const { theme, setTheme } = useTheme();

  // §14 Migration dialog state
  const [migrateDialog, setMigrateDialog] = useState<MigrateDialogState>(MIGRATE_DIALOG_CLOSED);
  const [migratePending, setMigratePending] = useState<Record<string, unknown> | null>(null);
  const [migrateLoading, setMigrateLoading] = useState(false);

  async function handleGenerateDiagnostics() {
    setDiagnosticsGenerating(true);
    try {
      const filePath = await generateDiagnosticsBundle();
      if (filePath) {
        await revealInOSFolder(filePath);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setDiagnosticsGenerating(false);
    }
  }

  const menus = (
    <>
      {/* App 메뉴 — mockup v5: 첫 메뉴는 앱명(kuro), 굵게. KURO 탭에서는 "kuro"만 노출. */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={`${TRIGGER_CLS} font-bold`}>{t("menuBar.appMenu.kuro")}</button>
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
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => { void getCurrentWindow().close(); }}>
            <span className="flex-1">{t("menuBar.appMenu.closeWindow")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}W</kbd>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => { void getCurrentWindow().destroy(); }}>
            <span className="flex-1">{t("menuBar.appMenu.quit")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY}Q</kbd>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Edit 메뉴 — Preferences 진입점 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={TRIGGER_CLS}>{t("menuBar.edit.title")}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={() => setPreferencesOpen(true)}>
            <span className="flex-1">{t("menuBar.edit.preferences")}</span>
            <kbd className="ml-4 text-caption text-muted-foreground">{MOD_KEY},</kbd>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* View 메뉴 */}
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
          {/* 1-C: Language 서브메뉴 */}
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              {t("menuBar.view.language")}
            </DropdownMenuSubTrigger>
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
          {/* 1-D: Theme 서브메뉴 */}
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>
              {t("menuBar.view.theme.title")}
            </DropdownMenuSubTrigger>
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
          {/* 1-E: Full screen */}
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

      {/* Run 메뉴 — Diagnostics + Replay + Check sidecar */}
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
          {/* 1-A: Replay saved run */}
          <DropdownMenuItem onClick={() => { void handleReplay(); }}>
            {t("menuBar.run.replay")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {/* 1-B: Check sidecar health (was incorrectly wired to handleCheckForUpdates) */}
          <DropdownMenuItem onClick={() => { void handleCheckSidecarHealth(); }}>
            {t("menuBar.run.checkSidecar")}
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

      <SettingsDialog open={preferencesOpen} onOpenChange={setPreferencesOpen} scope="kuro" />

      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} scope="kuro" />

      <SharedAboutDialog
        open={aboutOpen}
        onOpenChange={setAboutOpen}
        kind="kuro"
        onOpenShortcuts={() => setShortcutsOpen(true)}
      />

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
    </>
  );
}
