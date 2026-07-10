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
  UPDATE_CHECK_EVENT,
  type UpdateCheckResult,
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
          <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
            {t("about.later")}
          </Button>
          <Button size="sm" onClick={() => void handleOpenRelease()}>
            {t("about.viewRelease")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
