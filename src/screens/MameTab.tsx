import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MameAppLayout } from "@/components/mame/layout/MameAppLayout";
import { sendRequest } from "@/lib/ipc-mame";
import { listRecentProjects, loadProject } from "@/lib/project";
import { formatError } from "@/lib/utils";
import { useKumaProject } from "@/state/projectContext";

type MatchCandidate = { path: string; name: string };

export function MameTab() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const [match, setMatch] = useState<MatchCandidate | null>(null);
  /** Why the last Load attempt failed. Empty when there has been none. */
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const handler = async (ev: Event) => {
      const custom = ev as CustomEvent<{ path: string }>;
      const xlsxPath = custom.detail?.path;
      if (!xlsxPath) {
        return;
      }
      try {
        const meta = await sendRequest<{ project_id: string } | null>(
          "read_kuma_meta",
          { path: xlsxPath },
        );
        if (!meta || !meta.project_id) {
          return;
        }
        if (project?.project_id === meta.project_id) {
          return;
        }
        const recents = await listRecentProjects();
        const hit = recents.find((recent) => recent.project_id === meta.project_id);
        if (hit) {
          setMatch({ path: hit.path, name: hit.name });
        }
      } catch {
        // silent fallback to scratch
      }
    };

    window.addEventListener("kuma:mame-xlsx-dropped", handler as EventListener);
    return () => {
      window.removeEventListener("kuma:mame-xlsx-dropped", handler as EventListener);
    };
  }, [project?.project_id]);

  /** Dismiss the dialog, dropping any reason the last attempt left behind. */
  function closeMatch() {
    setMatch(null);
    setLoadError("");
  }

  /**
   * A failed load must not look like a cancel.
   *
   * The `finally` that used to close this dialog ran on rejection too, so a
   * project that could not be loaded produced exactly what the Cancel button
   * produces: the dialog gone, no event, nothing changed, nothing said. The
   * rejection then escaped through `void confirmLoad()` with no handler.
   *
   * So the dialog is closed only on success. On failure it stays open carrying
   * the reason, which leaves Cancel as the way out and keeps Load available for
   * a retry once the cause is fixed.
   */
  async function confirmLoad() {
    if (!match) {
      return;
    }
    setLoadError("");
    try {
      await loadProject(match.path);
      window.dispatchEvent(
        new CustomEvent("kuma:project-load-request", { detail: { path: match.path } }),
      );
      setMatch(null);
    } catch (err) {
      setLoadError(formatError(err));
    }
  }

  return (
    <>
      <MameAppLayout />
      <Dialog open={match !== null} onOpenChange={(open) => !open && closeMatch()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("mameTab.matchingProjectTitle")}</DialogTitle>
            <DialogDescription>
              {match ? t("mameTab.matchingProjectDescription", { name: match.name }) : ""}
            </DialogDescription>
          </DialogHeader>
          {loadError && (
            <p role="alert" data-testid="mame-tab-load-error" className="text-sm text-destructive">
              {loadError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={closeMatch}>
              {t("mameTab.cancelButton")}
            </Button>
            <Button onClick={() => void confirmLoad()}>{t("mameTab.loadButton")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
