import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { openUrl } from "@tauri-apps/plugin-opener";
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
  checkForLatestRelease,
  downloadAndInstallUpdate,
  isTauriRuntime,
  UPDATE_CHECK_EVENT,
  type UpdateCheckResult,
  type UpdateInstallProgress,
} from "@/lib/updateCheck";

let startupCheck: Promise<UpdateCheckResult> | null = null;

function requestLatestRelease(): Promise<UpdateCheckResult> {
  startupCheck ??= checkForLatestRelease(__APP_VERSION__).finally(() => {
    startupCheck = null;
  });
  return startupCheck;
}

export function UpdateAvailableDialog() {
  const { t } = useTranslation();
  const [update, setUpdate] = useState<UpdateCheckResult | null>(null);
  const [open, setOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<UpdateInstallProgress | null>(null);
  const mountedRef = useRef(true);

  const runCheck = useCallback(
    async (manual: boolean) => {
      if (manual) toast.info(t("about.checking"));
      try {
        const result = await requestLatestRelease();
        if (!mountedRef.current) return;
        if (result.updateAvailable) {
          setUpdate(result);
          setOpen(true);
        } else if (manual) {
          toast.success(t("about.upToDate", { version: result.currentVersion }));
        }
      } catch (error) {
        if (manual && mountedRef.current) {
          toast.error(
            t("about.updateCheckFailed", {
              message: error instanceof Error ? error.message : String(error),
            }),
          );
        }
      }
    },
    [t],
  );

  useEffect(() => {
    mountedRef.current = true;
    if (navigator.onLine) void runCheck(false);

    const handleManualCheck = () => {
      void runCheck(true);
    };
    window.addEventListener(UPDATE_CHECK_EVENT, handleManualCheck);
    return () => {
      mountedRef.current = false;
      window.removeEventListener(UPDATE_CHECK_EVENT, handleManualCheck);
    };
  }, [runCheck]);

  async function handleOpenRelease() {
    if (!update) return;
    try {
      await openUrl(update.releaseUrl);
      setOpen(false);
    } catch (error) {
      toast.error(
        t("about.updateCheckFailed", {
          message: error instanceof Error ? error.message : String(error),
        }),
      );
    }
  }

  async function handleInstall() {
    if (!update || installing) return;
    setInstalling(true);
    setProgress(null);
    try {
      const applied = await downloadAndInstallUpdate((p) => {
        if (mountedRef.current) setProgress(p);
      });
      if (!applied) {
        // No updater artifact for this target (e.g. .deb): fall back to the
        // release page instead of leaving the user stuck.
        await handleOpenRelease();
      }
      // On success the app relaunches; no further UI update needed.
    } catch (error) {
      if (mountedRef.current) {
        toast.error(
          t("about.updateInstallFailed", {
            message: error instanceof Error ? error.message : String(error),
          }),
        );
      }
    } finally {
      if (mountedRef.current) {
        setInstalling(false);
        setProgress(null);
      }
    }
  }

  function progressLabel(): string {
    if (!progress) return t("about.updateInstalling");
    if (progress.phase === "downloading") {
      if (progress.contentLength && progress.downloaded !== undefined) {
        const pct = Math.min(
          100,
          Math.round((progress.downloaded / progress.contentLength) * 100),
        );
        return t("about.updateDownloadingPct", { pct });
      }
      return t("about.updateDownloading");
    }
    if (progress.phase === "relaunching") return t("about.updateRelaunching");
    return t("about.updateInstalling");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>
            {update
              ? t("about.updateAvailable", {
                  current: update.currentVersion,
                  next: update.latestVersion,
                })
              : t("about.checkForUpdates")}
          </DialogTitle>
          <DialogDescription>{t("about.updateRecommendation")}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={installing}
          >
            {t("about.later")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleOpenRelease()}
            disabled={installing}
          >
            {t("about.viewRelease")}
          </Button>
          {isTauriRuntime() && (
            <Button
              size="sm"
              onClick={() => void handleInstall()}
              disabled={installing}
              aria-busy={installing}
            >
              {installing ? progressLabel() : t("about.updateNow")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
