/**
 * SettingsDialog — 앱 전역 설정 다이얼로그 (Phase 3 확장)
 *
 * Tabs: General / Network / Sidecar
 * - General: Language, Theme, Accessibility, Notifications, Data folder
 * - Network: Offline mode + 4 per-service consent checkboxes
 * - Sidecar: Persist on cancel
 *
 * There is no Telemetry tab. It held two opt-in flags for sending crash logs
 * and usage data, nothing read either one, and section 10 of the frontend
 * standards makes zero outbound telemetry release-blocking, so implementing
 * them was never an option. Diagnostics travel as the local zip the Run menu
 * writes, which is what section 16 asks for.
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
import { revealInOSFolder } from "../../lib/openFolder";
import { formatCodonTableMessage } from "../../lib/codonTableMessages";
import { useAppStore } from "../../store/appStore";
import { mapThemeToBundle } from "../../store/slices/settingsSlice";

// §8 A11y: colorblind mode localStorage key (shared with MenuBar)
/**
 * Settings a user can change that nothing in the app reads.
 *
 * Empty, and worth keeping empty. A control that stores a preference and
 * changes no behaviour is a promise the app does not keep, which is how a run
 * pinned to an 18 nt primer floor came back with 17mers: the fill-on-failure
 * box read as a gate and gated nothing. An audit found five more here. Four
 * were removed outright, because nothing could honour them and in two cases
 * nothing ever should (docs/standards/common-frontend-standards.md section 10
 * makes zero outbound telemetry release-blocking); the fifth, keeping partial
 * results on cancel, was implemented instead.
 *
 * A setting that cannot be honoured yet belongs in this list and renders
 * disabled with settings.inactiveHint next to it, rather than looking active.
 * tests/sidecar_kuro/test_settings_contract.py compares this list against the
 * settings model and fails on either drift.
 */
export const INACTIVE_SETTINGS: readonly string[] = [];

const CB_KEY = "kuma:kuro:colorblindMode";

/**
 * The seed file `handle_list_organisms` writes into the codon-table folder
 * (`_CODON_SEED_FILES` in python-core/sidecar_kuro/handlers/misc.py).
 *
 * `revealItemInDir` selects an ITEM inside its parent, so handing it the folder
 * itself would open the folder's parent with the folder highlighted. Pointing
 * at a file the backend guarantees exists opens the codon-table folder itself,
 * which is what a user who has never installed a table needs to see.
 */
const CODON_SEED_FILE = "README.txt";

/**
 * Join a sidecar-resolved directory with a file name using the separator that
 * directory already uses. `user_dir` comes from Python's `Path`, so it carries
 * backslashes on Windows and forward slashes elsewhere, and there is no
 * `path.join` in the renderer.
 */
function joinCodonDir(dir: string, name: string): string {
  const sep = dir.includes("\\") && !dir.includes("/") ? "\\" : "/";
  return dir.endsWith(sep) ? `${dir}${name}` : `${dir}${sep}${name}`;
}

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

  // §6 Settings: user codon tables. `loadOrganisms` IS the refresh action -
  // `handle_list_organisms` drops the registry caches, seeds the folder and
  // re-reads both directories before answering - so Refresh needs no RPC of
  // its own and the dropdown updates from the same call.
  const organisms = useAppStore((s) => s.organisms);
  const codonTableFailures = useAppStore((s) => s.codonTableFailures);
  const codonTableDir = useAppStore((s) => s.codonTableDir);
  const loadOrganisms = useAppStore((s) => s.loadOrganisms);
  const [codonRefreshing, setCodonRefreshing] = useState(false);
  const [codonOpenFailed, setCodonOpenFailed] = useState(false);

  // No listing is triggered on open. AppLayout already calls loadOrganisms once
  // the sidecar reports ready, and firing it from here would run before that on
  // a cold start, where it rejects and writes "Organism list load failed" into
  // the status bar for a dialog the user merely opened. Until that first
  // listing lands the path line shows the loading placeholder and Refresh is
  // the way out.

  async function handleCodonRefresh() {
    setCodonRefreshing(true);
    try {
      await loadOrganisms();
    } finally {
      setCodonRefreshing(false);
    }
  }

  async function handleCodonOpenFolder() {
    if (codonTableDir === null) return;
    setCodonOpenFailed(false);
    try {
      await revealInOSFolder(joinCodonDir(codonTableDir, CODON_SEED_FILE));
    } catch {
      // The opener plugin is absent in the mock harness and an OS can refuse.
      // Neither is worth a toast, but a dead button is worse than a message.
      setCodonOpenFailed(true);
    }
  }

  const userTables = organisms.filter((o) => o.source === "user");
  const builtinCount = organisms.length - userTables.length;
  const advisories = userTables.filter((o) => o.warnings.length > 0);

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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t("settings.title")}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto pr-1 -mr-1">
        <Tabs defaultValue="general" className="w-full">
          <TabsList className="w-full grid grid-cols-2">
            <TabsTrigger value="general" className="min-w-0 truncate">{t("settings.tab.general")}</TabsTrigger>
            <TabsTrigger value="network" className="min-w-0 truncate">{t("settings.tab.network")}</TabsTrigger>
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

            {/* §6 User codon tables (drop-in folder) */}
            <section aria-labelledby="settings-codontables-heading" className="flex flex-col gap-1.5">
              <p id="settings-codontables-heading" className="text-sm font-semibold text-foreground">
                {t("settings.codonTables.title")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("settings.codonTables.hint")}
              </p>
              <p
                className="font-mono text-xs text-muted-foreground break-all"
                title={codonTableDir ?? undefined}
              >
                {codonTableDir ?? t("settings.dataFolderLoading")}
              </p>
              <p className="text-xs text-muted-foreground">
                {t("settings.codonTables.counts", {
                  builtin: builtinCount,
                  user: userTables.length,
                })}
              </p>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={codonTableDir === null}
                  onClick={() => void handleCodonOpenFolder()}
                >
                  {t("settings.codonTables.openFolder")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={codonRefreshing}
                  onClick={() => void handleCodonRefresh()}
                >
                  {t("settings.codonTables.refresh")}
                </Button>
              </div>
              {codonOpenFailed && (
                <p className="text-xs text-warning">
                  {t("settings.codonTables.openFolderFailed")}
                </p>
              )}
              {codonTableFailures.length > 0 && (
                <div className="flex flex-col gap-1 rounded-control border border-warning/30 bg-warning/5 p-2">
                  <p className="text-xs font-medium text-foreground">
                    {t("settings.codonTables.notLoaded")}
                  </p>
                  {/* `failed[]` carries no `params`, only the first rule code and
                      the backend's English detail, so these lines name the code
                      and quote the reason rather than rebuilding a sentence. */}
                  {codonTableFailures.map((f) => (
                    <p key={f.filename} className="text-xs text-muted-foreground break-words">
                      {t("settings.codonTables.notLoadedEntry", {
                        filename: f.filename,
                        code: f.code,
                        reason: f.reason,
                      })}
                    </p>
                  ))}
                </div>
              )}
              {advisories.length > 0 && (
                <div className="flex flex-col gap-1 rounded-control border border-border bg-muted/40 p-2">
                  <p className="text-xs font-medium text-foreground">
                    {t("settings.codonTables.advisories")}
                  </p>
                  {advisories.map((o) => (
                    <div key={o.key} className="flex flex-col gap-0.5">
                      <p className="font-mono text-xs text-foreground">{o.key}</p>
                      {o.warnings.map((w, i) => (
                        <p key={`${o.key}-${w.code}-${i}`} className="text-xs text-muted-foreground break-words">
                          {formatCodonTableMessage(t, w.code, w.params)}
                        </p>
                      ))}
                    </div>
                  ))}
                </div>
              )}
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
                    // Absent means enabled: SettingsNetwork in
                    // python-core/sidecar_kuro/models.py defaults every
                    // consent_* to True, so `?? false` drew four unchecked
                    // boxes over a bundle that said the opposite.
                    checked={settings?.network?.[key] ?? true}
                    onChange={(e) => handleConsentChange(key, e.target.checked)}
                    className="h-4 w-4 accent-primary"
                  />
                  <span className="text-foreground">{t(labelKey)}</span>
                </label>
              ))}
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
