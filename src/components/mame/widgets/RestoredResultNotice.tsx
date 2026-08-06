/**
 * RestoredResultNotice — says which build produced the results on screen.
 *
 * A restored project replays the analyze response it saved, so the review
 * screen can show verdicts nobody ran in this session. That is the feature:
 * sequencing turnaround is measured in weeks. It stops being harmless the
 * moment the two builds disagree, and between v0.15.10 and v0.15.18 they did:
 * a workbook that writes one plate two ways is now refused, replicate picks are
 * ordered by measured purity, a finished run is checked against itself, and
 * result rows follow the plate column. A result scored before those changes is
 * not what this build would produce.
 *
 * The result is still restored and still exported: throwing away an operator's
 * run because the app updated would be worse than showing it. What changes is
 * that the screen states the origin and offers the two honest ways out, re-run
 * or keep. "Keep" is remembered per project and per producing version, so the
 * notice does not nag every restart but does speak up for a different snapshot.
 *
 * Deliberately not an error: the data is intact and may well be correct. It is
 * a warning about provenance, which is why it renders as one.
 */

import { useMemo, useState } from "react";
import { History, RefreshCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  acknowledgeResultVersion,
  hasAcknowledgedResultVersion,
} from "@/lib/mame/resultProvenance";
import { useKumaProject } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";

interface RestoredResultNoticeProps {
  /**
   * Re-run trigger, wired to the same pre-flighted callback the Run button
   * uses. Omitted where a run cannot be started from that screen, in which case
   * the notice still states the origin and offers only "keep".
   */
  onRunRequest?: () => void;
}

export function RestoredResultNotice({ onRunRequest }: RestoredResultNoticeProps = {}) {
  const { t } = useTranslation();
  const project = useKumaProject();
  const provenance = useMameAppStore((s) => s.restoredResultProvenance);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const setProvenance = useMameAppStore((s) => s.setRestoredResultProvenance);
  const projectPath = project?.path ?? null;
  const version = provenance?.version ?? null;
  // Bumped by the Keep button. The stored answer is re-read whenever the
  // project or the producing version changes, because this component stays
  // mounted while the operator switches projects: a mount-time latch would
  // carry one project's dismissal into the next project's stale snapshot.
  const [ackTick, setAckTick] = useState(0);
  const dismissed = useMemo(
    () =>
      provenance !== null &&
      projectPath !== null &&
      hasAcknowledgedResultVersion(projectPath, version),
    // ackTick is the invalidation signal for the localStorage read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [provenance, projectPath, version, ackTick],
  );

  if (!provenance || dismissed) return null;

  const body =
    provenance.relation === "unknown" || version === null
      ? t("mame.restoredResult.bodyUnknown")
      : provenance.relation === "newer"
        ? t("mame.restoredResult.bodyNewer", { version })
        : t("mame.restoredResult.bodyOlder", { version });

  function keepThem() {
    if (projectPath) acknowledgeResultVersion(projectPath, version);
    setAckTick((tick) => tick + 1);
  }

  function rerun() {
    // The run itself clears the restored result (clearResults), but clearing the
    // flag here too keeps the notice from lingering while the run starts.
    setProvenance(null);
    onRunRequest?.();
  }

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
        <div className="flex flex-wrap gap-2 pt-0.5">
          {onRunRequest && (
            <Button
              variant="outline"
              size="sm"
              className="h-control gap-1.5 rounded-control text-caption"
              onClick={rerun}
              disabled={isAnalyzing}
            >
              <RefreshCw size={12} aria-hidden="true" />
              {t("mame.restoredResult.rerun")}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-control gap-1.5 rounded-control text-caption"
            onClick={keepThem}
          >
            <X size={12} aria-hidden="true" />
            {t("mame.restoredResult.keep")}
          </Button>
        </div>
      </div>
    </div>
  );
}
