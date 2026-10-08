/**
 * Single source of truth for rendering a MAME analyze run duration.
 *
 * Both the step 2.1 completion popup (AnalyzeDurationDialog) and the resident
 * step 2.2 readout (SummaryRow) call this, so the two can never disagree about
 * how long the same run took.
 */

/**
 * Render a run duration in the units a reader actually wants.
 *
 * The request was "how many minutes", but a sub-minute run rendered as
 * "0 min 47 s" reads as a bug, and a whole-minute run rendered as "3 min 0 s"
 * reads as noise. So: minutes lead whenever there is at least one, seconds are
 * dropped when they are zero, and a run under a minute is reported in seconds
 * alone. Seconds are rounded (not truncated) so a 59.6 s run reports "1 min"
 * rather than "59 s".
 */
export function formatRunDuration(
  durationMs: number,
  t: (key: string, vars?: Record<string, number>) => string,
): string {
  const totalSec = Math.max(0, Math.round(durationMs / 1000));
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min === 0) return t("mame.analyze.duration.secOnly", { sec });
  if (sec === 0) return t("mame.analyze.duration.minOnly", { min });
  return t("mame.analyze.duration.minSec", { min, sec });
}
