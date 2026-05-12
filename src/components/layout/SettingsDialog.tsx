/**
 * SettingsDialog — 앱 전역 설정 다이얼로그
 *
 * 기존 About 다이얼로그에서 분리된 항목들:
 * - Accessibility (Colorblind mode toggle)
 * - Notifications 설정
 * - Data folder 경로 표시 + 열기 버튼
 * - Keyboard shortcuts 표
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
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import { LocaleToggle } from "../ui/LocaleToggle";
import { notificationPermissionGranted, requestNotificationPermission } from "../../lib/notify";
import { getConfig } from "../../lib/project";
import { getShortcutsFor } from "../../lib/shortcuts";

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

  const shortcuts = getShortcutsFor(scope);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("settings.title")}</DialogTitle>
        </DialogHeader>

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

        {/* Keyboard shortcuts */}
        <section aria-labelledby="settings-shortcuts-heading" className="flex flex-col gap-1.5">
          <p id="settings-shortcuts-heading" className="text-sm font-semibold text-foreground">
            {t("settings.keyboardShortcuts")}
          </p>
          <table className="w-full text-xs border-collapse" role="table">
            <thead>
              <tr className="border-b border-border">
                <th scope="col" className="py-0.5 pr-3 text-left font-semibold text-muted-foreground">
                  {t("settings.shortcutKeys")}
                </th>
                <th scope="col" className="py-0.5 text-left font-semibold text-muted-foreground">
                  {t("settings.shortcutAction")}
                </th>
              </tr>
            </thead>
            <tbody>
              {shortcuts.map((s) => (
                <tr key={s.keys} className="border-b border-border/40 last:border-0">
                  <td className="py-0.5 pr-3 font-mono text-foreground">{s.keys}</td>
                  <td className="py-0.5 text-muted-foreground">{s.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
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

        <DialogFooter>
          <Button size="sm" onClick={() => onOpenChange(false)}>
            {t("settings.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
