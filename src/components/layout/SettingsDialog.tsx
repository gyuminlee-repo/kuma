/**
 * SettingsDialog — 앱 전역 설정 다이얼로그 (Phase 3 확장)
 *
 * Tabs: General / Network / Sidecar / Telemetry
 * - General: Language, Theme, Accessibility, Notifications, Data folder
 * - Network: Offline mode + 4 consent checkboxes
 * - Sidecar: Concurrency, Cancel timeout, Persist on cancel
 * - Telemetry: Crash log auto-send, Anonymous stats
 *
 * 변경 즉시 적용 (debounce 500ms 자동 저장, Apply 버튼 없음).
 */
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../ui/dialog";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../ui/tabs";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import { LocaleToggle } from "../ui/LocaleToggle";
import { useTheme } from "../ui/ThemeToggle";
import type { Theme } from "../ui/ThemeToggle";
import { notificationPermissionGranted, requestNotificationPermission } from "../../lib/notify";
import { getConfig } from "../../lib/project";
import { useAppStore } from "../../store/appStore";
import { mapThemeToBundle } from "../../store/slices/settingsSlice";

// §8 A11y: colorblind mode localStorage key (shared with MenuBar)
const CB_KEY = "kuma:kuro:colorblindMode";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 단축키 표시 범위. 기본 "kuro" */
  scope?: "kuro" | "mame";
}

export function SettingsDialog({ open, onOpenChange, scope = "kuro" }: SettingsDialogProps) {
  const { t } = useTranslation();

  // settingsSlice
  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const lastSavedAt = useAppStore((s) => s.lastSavedAt);

  // networkConsentSlice (offlineMode canonical source — synced via settingsSlice.loadSettings)
  const offlineMode = useAppStore((s) => s.offlineMode);
  const setOfflineMode = useAppStore((s) => s.setOfflineMode);

  // §8 A11y: colorblind mode
  const [colorblindMode, setColorblindModeState] = useState<boolean>(
    () => localStorage.getItem(CB_KEY) === "true",
  );

  function toggleColorblindMode(val: boolean) {
    setColorblindModeState(val);
    localStorage.setItem(CB_KEY, String(val));
    window.dispatchEvent(new CustomEvent("kuma:colorblindMode", { detail: val }));
  }

  // §3 Notifications
  const [notifyPermission, setNotifyPermission] = useState<boolean | null>(null);

  useEffect(() => {
    void notificationPermissionGranted().then(setNotifyPermission);
  }, []);

  async function handleEnableNotifications() {
    const granted = await requestNotificationPermission();
    setNotifyPermission(granted);
  }

  // §6 Settings: data folder
  const [dataFolder, setDataFolder] = useState<string | null>(null);

  useEffect(() => {
    if (!open || dataFolder !== null) return;
    void getConfig()
      .then((cfg) => setDataFolder(cfg.projects_root))
      .catch(() => setDataFolder("unknown"));
  }, [open, dataFolder]);

  // Theme (ThemeToggle hook — single source of truth for localStorage)
  const { theme, setTheme } = useTheme();

  function handleThemeChange(next: Theme) {
    setTheme(next);
    updateSettings({ theme: mapThemeToBundle(next) });
  }

  // scope 는 향후 도구별 분기용 보존
  void scope;

  // savedAt 표시용 시간 문자열
  const savedAtStr = lastSavedAt
    ? new Date(lastSavedAt).toLocaleTimeString()
    : null;

  // ── Network helpers ─────────────────────────────────────────────────────────

  function handleOfflineModeChange(val: boolean) {
    setOfflineMode(val);
    updateSettings({ network: { ...settings?.network, offline_mode: val } });
  }

  function handleConsentChange(
    key: "consent_uniprot" | "consent_blast" | "consent_alphafold" | "consent_interpro",
    val: boolean,
  ) {
    updateSettings({ network: { ...settings?.network, [key]: val } });
  }

  // ── Sidecar helpers ─────────────────────────────────────────────────────────

  function handleConcurrencyChange(val: number) {
    const clamped = Math.max(1, Math.min(16, val));
    updateSettings({ sidecar: { ...settings?.sidecar, concurrency_default: clamped } });
  }

  function handleCancelTimeoutChange(val: number) {
    const clamped = Math.max(5, Math.min(120, val));
    updateSettings({ sidecar: { ...settings?.sidecar, cancel_timeout_secs: clamped } });
  }

  function handlePersistOnCancelChange(val: "partial" | "discard") {
    updateSettings({ sidecar: { ...settings?.sidecar, persist_on_cancel: val } });
  }

  // ── Telemetry helpers ───────────────────────────────────────────────────────

  function handleCrashLogAutoSendChange(val: boolean) {
    updateSettings({ telemetry: { ...settings?.telemetry, crash_log_auto_send: val } });
  }

  function handleAnonymousStatsChange(val: boolean) {
    updateSettings({ telemetry: { ...settings?.telemetry, anonymous_stats: val } });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t("settings.title")}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto pr-1 -mr-1">
        <Tabs defaultValue="general" className="w-full">
          <TabsList className="w-full grid grid-cols-4">
            <TabsTrigger value="general" className="min-w-0 truncate">{t("settings.tab.general")}</TabsTrigger>
            <TabsTrigger value="network" className="min-w-0 truncate">{t("settings.tab.network")}</TabsTrigger>
            <TabsTrigger value="sidecar" className="min-w-0 truncate">{t("settings.tab.sidecar")}</TabsTrigger>
            <TabsTrigger value="telemetry" className="min-w-0 truncate">{t("settings.tab.telemetry")}</TabsTrigger>
          </TabsList>

          {/* ── General ──────────────────────────────────────────────────────── */}
          <TabsContent value="general" className="flex flex-col gap-4 pt-3">

            {/* Theme */}
            <section aria-labelledby="settings-theme-heading" className="flex flex-col gap-1.5">
              <p id="settings-theme-heading" className="text-sm font-semibold text-foreground">
                {t("settings.theme.label")}
              </p>
              <div className="flex gap-2" role="radiogroup" aria-labelledby="settings-theme-heading">
                {(["light", "dark", "system"] as Theme[]).map((th) => (
                  <button
                    key={th}
                    type="button"
                    role="radio"
                    aria-checked={theme === th}
                    onClick={() => handleThemeChange(th)}
                    className={[
                      "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                      theme === th
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-background text-foreground hover:bg-accent",
                    ].join(" ")}
                  >
                    {th === "light"
                      ? t("settings.theme.light")
                      : th === "dark"
                      ? t("settings.theme.dark")
                      : t("settings.theme.auto")}
                  </button>
                ))}
              </div>
            </section>

            {/* Language */}
            <section aria-labelledby="settings-language-heading" className="flex flex-col gap-1.5">
              <p id="settings-language-heading" className="text-sm font-semibold text-foreground">
                {t("settings.language")}
              </p>
              <div className="flex items-center gap-2">
                <Label htmlFor="settings-locale-toggle" className="sr-only">
                  {t("settings.languageSelectionLabel")}
                </Label>
                <LocaleToggle variant="icon-label" />
              </div>
              <p className="text-xs text-muted-foreground">
                {t("settings.languageNote")}
              </p>
            </section>

            {/* §8 Accessibility */}
            <section aria-labelledby="settings-accessibility-heading" className="flex flex-col gap-1.5">
              <p id="settings-accessibility-heading" className="text-sm font-semibold text-foreground">
                {t("settings.accessibility")}
              </p>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  id="settings-colorblind-mode"
                  checked={colorblindMode}
                  onChange={(e) => toggleColorblindMode(e.target.checked)}
                  className="h-3.5 w-3.5 accent-primary"
                  aria-describedby="settings-colorblind-desc"
                />
                <span className="text-foreground">{t("settings.colorblindMode")}</span>
              </label>
              <p id="settings-colorblind-desc" className="text-xs text-muted-foreground pl-5">
                {t("settings.colorblindModeDesc")}
              </p>
            </section>

            {/* §3 Notifications */}
            <section aria-labelledby="settings-notifications-heading" className="flex flex-col gap-1">
              <p id="settings-notifications-heading" className="text-sm font-semibold text-foreground">
                {t("settings.notifications")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("settings.notificationsStatus")}{" "}
                <span
                  className={notifyPermission ? "text-success font-medium" : "text-warning font-medium"}
                >
                  {notifyPermission ? t("settings.notificationsEnabled") : t("settings.notificationsDisabled")}
                </span>
              </p>
              {!notifyPermission && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleEnableNotifications()}
                >
                  {t("settings.enableNotifications")}
                </Button>
              )}
              <p className="text-xs text-muted-foreground">
                {t("settings.notificationsNote")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("settings.sleepPrevention")}
              </p>
            </section>

            {/* §6 Data folder */}
            <section aria-labelledby="settings-datafolder-heading" className="flex flex-col gap-1.5">
              <p id="settings-datafolder-heading" className="text-sm font-semibold text-foreground">
                {t("settings.dataFolder")}
              </p>
              <p
                className="font-mono text-xs text-muted-foreground break-all"
                title={dataFolder ?? undefined}
              >
                {dataFolder ?? t("settings.dataFolderLoading")}
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  onOpenChange(false);
                  window.dispatchEvent(new CustomEvent("kuma:show-onboarding"));
                }}
              >
                {t("settings.dataFolderChange")}
              </Button>
            </section>
          </TabsContent>

          {/* ── Network ──────────────────────────────────────────────────────── */}
          <TabsContent value="network" className="flex flex-col gap-4 pt-3">

            {/* Offline mode */}
            <section aria-labelledby="settings-network-offline-heading" className="flex flex-col gap-1.5">
              <p id="settings-network-offline-heading" className="text-sm font-semibold text-foreground">
                {t("settings.network.offlineMode")}
              </p>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  id="settings-offline-mode"
                  checked={offlineMode}
                  onChange={(e) => handleOfflineModeChange(e.target.checked)}
                  className="h-4 w-4 accent-primary"
                />
                <span className="text-foreground">{t("settings.network.offlineMode")}</span>
              </label>
              <p className="text-xs text-muted-foreground">
                {t("settings.network.offlineModeHint")}
              </p>
            </section>

            {/* External service consent */}
            <section aria-labelledby="settings-consent-heading" className="flex flex-col gap-2">
              <p id="settings-consent-heading" className="text-sm font-semibold text-foreground">
                {t("settings.network.consent.title")}
              </p>
              {(
                [
                  { key: "consent_uniprot", labelKey: "settings.network.consent.uniprot" },
                  { key: "consent_blast", labelKey: "settings.network.consent.blast" },
                  { key: "consent_alphafold", labelKey: "settings.network.consent.alphafold" },
                  { key: "consent_interpro", labelKey: "settings.network.consent.interpro" },
                ] as const
              ).map(({ key, labelKey }) => (
                <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings?.network?.[key] ?? false}
                    onChange={(e) => handleConsentChange(key, e.target.checked)}
                    className="h-4 w-4 accent-primary"
                  />
                  <span className="text-foreground">{t(labelKey)}</span>
                </label>
              ))}
            </section>
          </TabsContent>

          {/* ── Sidecar ──────────────────────────────────────────────────────── */}
          <TabsContent value="sidecar" className="flex flex-col gap-4 pt-3">

            {/* Concurrency */}
            <section aria-labelledby="settings-concurrency-heading" className="flex flex-col gap-1.5">
              <label
                id="settings-concurrency-heading"
                htmlFor="settings-concurrency"
                className="text-sm font-semibold text-foreground"
              >
                {t("settings.sidecar.concurrency")}
              </label>
              <input
                id="settings-concurrency"
                type="number"
                min={1}
                max={16}
                value={settings?.sidecar?.concurrency_default ?? 4}
                onChange={(e) => handleConcurrencyChange(Number(e.target.value))}
                className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-describedby="settings-concurrency-hint"
              />
              <p id="settings-concurrency-hint" className="text-xs text-muted-foreground">
                {t("settings.sidecar.concurrencyHint")}
              </p>
            </section>

            {/* Cancel timeout */}
            <section aria-labelledby="settings-cancel-timeout-heading" className="flex flex-col gap-1.5">
              <label
                id="settings-cancel-timeout-heading"
                htmlFor="settings-cancel-timeout"
                className="text-sm font-semibold text-foreground"
              >
                {t("settings.sidecar.cancelTimeout")}
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="settings-cancel-timeout"
                  type="number"
                  min={5}
                  max={120}
                  value={settings?.sidecar?.cancel_timeout_secs ?? 30}
                  onChange={(e) => handleCancelTimeoutChange(Number(e.target.value))}
                  className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-describedby="settings-cancel-timeout-hint"
                />
                <span className="text-sm text-muted-foreground">sec</span>
              </div>
              <p id="settings-cancel-timeout-hint" className="text-xs text-muted-foreground">
                {t("settings.sidecar.cancelTimeoutHint")}
              </p>
            </section>

            {/* Persist on cancel */}
            <section aria-labelledby="settings-persist-heading" className="flex flex-col gap-2">
              <p id="settings-persist-heading" className="text-sm font-semibold text-foreground">
                {t("settings.sidecar.persistOnCancel")}
              </p>
              <div className="flex flex-col gap-1.5" role="radiogroup" aria-labelledby="settings-persist-heading">
                {(["partial", "discard"] as const).map((val) => (
                  <label key={val} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name="settings-persist-on-cancel"
                      value={val}
                      checked={(settings?.sidecar?.persist_on_cancel ?? "partial") === val}
                      onChange={() => handlePersistOnCancelChange(val)}
                      className="accent-primary"
                    />
                    <span className="text-foreground">
                      {val === "partial"
                        ? t("settings.sidecar.persistPartial")
                        : t("settings.sidecar.persistDiscard")}
                    </span>
                  </label>
                ))}
              </div>
            </section>
          </TabsContent>

          {/* ── Telemetry ─────────────────────────────────────────────────────── */}
          <TabsContent value="telemetry" className="flex flex-col gap-4 pt-3">

            {/* Crash log auto-send */}
            <section aria-labelledby="settings-crashlog-heading" className="flex flex-col gap-1.5">
              <p id="settings-crashlog-heading" className="text-sm font-semibold text-foreground">
                {t("settings.telemetry.crashLog")}
              </p>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  id="settings-crashlog-auto"
                  checked={settings?.telemetry?.crash_log_auto_send ?? false}
                  onChange={(e) => handleCrashLogAutoSendChange(e.target.checked)}
                  className="h-4 w-4 accent-primary"
                  aria-describedby="settings-crashlog-hint"
                />
                <span className="text-foreground">{t("settings.telemetry.crashLog")}</span>
              </label>
              <p id="settings-crashlog-hint" className="text-xs text-muted-foreground">
                {t("settings.telemetry.crashLogHint")}
              </p>
            </section>

            {/* Anonymous stats */}
            <section aria-labelledby="settings-anon-heading" className="flex flex-col gap-1.5">
              <p id="settings-anon-heading" className="text-sm font-semibold text-foreground">
                {t("settings.telemetry.anonymousStats")}
              </p>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  id="settings-anon-stats"
                  checked={settings?.telemetry?.anonymous_stats ?? false}
                  onChange={(e) => handleAnonymousStatsChange(e.target.checked)}
                  className="h-4 w-4 accent-primary"
                  aria-describedby="settings-anon-hint"
                />
                <span className="text-foreground">{t("settings.telemetry.anonymousStats")}</span>
              </label>
              <p id="settings-anon-hint" className="text-xs text-muted-foreground">
                {t("settings.telemetry.anonymousStatsHint")}
              </p>
            </section>
          </TabsContent>
        </Tabs>
        </div>

        <DialogFooter className="flex items-center justify-between">
          {savedAtStr && (
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {t("settings.savedAt", { time: savedAtStr })}
            </p>
          )}
          <Button size="sm" onClick={() => onOpenChange(false)}>
            {t("settings.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
