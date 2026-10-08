/**
 * RestoredResultNotice — a saved run this build will not show.
 *
 * A project folder outlives the app that made it, and MAME keeps changing what
 * a run produces: a workbook that describes one plate two ways is refused,
 * replicate picks are ordered by measured purity, a finished run is checked
 * against itself, result rows follow the plate column, a barcode file that does
 * not describe the plate stops the run. A result scored before those changes is
 * another build's answer.
 *
 * The list is the argument: an operator told to spend an hour re-analysing is
 * owed the changes that make the saved run obsolete.
 *
 * v0.15.20 showed it anyway, with a warning and a "keep these results" button.
 * That was wrong: a result the app lets you go on reading is a result the app
 * is telling you to trust, and the button quietly recommended running the lab
 * on an obsolete engine. There is no keep. The saved file is left on disk
 * untouched, the screen shows no verdicts, and the way to a result is a re-run
 * by this build.
 *
 * Not an error boundary: nothing failed and nothing was lost. It is a statement
 * about what the app is willing to present as current.
 */

import { History, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useMameAppStore } from "@/store/mame/mameAppStore";

interface RestoredResultNoticeProps {
  /**
   * Re-run trigger, wired to the same pre-flighted callback the Run button
   * uses. Omitted where a run cannot be started from that screen, in which case
   * the notice still states why nothing is shown.
   */
  onRunRequest?: () => void;
}

export function RestoredResultNotice({ onRunRequest }: RestoredResultNoticeProps = {}) {
  const { t } = useTranslation();
  const provenance = useMameAppStore((s) => s.restoredResultProvenance);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const canRun = useMameAppStore((s) => s.verdicts.length === 0);

  if (!provenance) return null;

  const version = provenance.version;
  const body =
    provenance.relation === "unknown" || version === null
      ? t("mame.restoredResult.bodyUnknown")
      : provenance.relation === "newer"
        ? t("mame.restoredResult.bodyNewer", { version })
        : t("mame.restoredResult.bodyOlder", { version });

  return (
    <div
      data-testid="restored-result-notice"
      data-relation={provenance.relation}
      role="status"
      aria-live="polite"
      className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/8 px-2.5 py-1.5"
    >
      <History size={12} className="mt-0.5 flex-shrink-0 text-warning" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1 text-caption text-foreground">
        <p className="font-medium break-words">{t("mame.restoredResult.title")}</p>
        <p className="break-words text-muted-foreground">{body}</p>
        {provenance.changes.length > 0 && (
          <p className="break-words text-muted-foreground">{t("mame.restoredResult.why")}</p>
        )}
        {provenance.changes.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {provenance.changes.map((change) => (
              <li key={change.revision} className="break-words">
                {t(`mame.restoredResult.change.${change.key}`)}
              </li>
            ))}
          </ul>
        )}
        <p className="break-words text-muted-foreground">
          {t("mame.restoredResult.fileKept")}
        </p>
        {onRunRequest && canRun && (
          <div className="pt-0.5">
            <Button
              variant="outline"
              size="sm"
              className="h-control gap-1.5 rounded-control text-caption"
              onClick={onRunRequest}
              disabled={isAnalyzing}
            >
              <RefreshCw size={12} aria-hidden="true" />
              {t("mame.restoredResult.rerun")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
