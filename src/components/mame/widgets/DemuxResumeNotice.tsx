/**
 * DemuxResumeNotice, how much of the result on screen predates this run.
 *
 * The per-NB demux writes a completion marker per native barcode, and a later
 * run in the same export folder reseeds a unit from its marker instead of
 * re-demuxing it whenever the marker reference/parameter fingerprint matches
 * (`kuma_core/mame/ingest/combinatorial_demux.py`, `marker_inputs_match`).
 * That gating makes reuse correct, so this is provenance and not a warning:
 * it is the only place an operator can see that part of what follows was
 * produced by an earlier run, which is what once made a "why does this look
 * wrong" question take far too long to answer.
 *
 * Silent in three states, all of which mean "nothing to report" rather than
 * zero: no run has completed since the last reset, the run mode wrote no
 * per-unit markers (consensus-dir and single-pool), or every unit was
 * recomputed here.
 */

import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

export function DemuxResumeNotice() {
  const { t } = useTranslation();
  const demuxResume = useMameAppStore((s) => s.demuxResume);

  if (demuxResume === null) return null;
  const reused = demuxResume.reused_units;
  if (reused <= 0) return null;
  const recomputed = demuxResume.recomputed_units;

  return (
    <div
      role="status"
      data-testid="demux-resume-notice"
      className="rounded-control border border-border bg-muted/40 px-3 py-2 text-caption text-muted-foreground"
    >
      {t("mame.analyze.demuxResume.line", {
        reused,
        total: reused + recomputed,
        recomputed,
      })}
    </div>
  );
}
