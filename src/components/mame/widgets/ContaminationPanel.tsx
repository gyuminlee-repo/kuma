/**
 * ContaminationPanel, what the demux matrix saw outside the campaign.
 *
 * The demux counts reads for every barcode combination, not only the ones the
 * plate occupies, and until now that breakdown was computed and dropped before
 * anything could read it. The one crosstalk check MAME had left
 * (`health.detect_cross_talk`) reads `barcode_distribution`, which on the
 * raw-run path is keyed by native barcode rather than by well, so the check
 * skipped in silence on exactly the runs it was written for.
 *
 * Two rules this panel exists to keep:
 *
 * - An unavailable signal shows its REASON, never a zero. A question that could
 *   not be asked has no answer, and a 0 in its place reads as a clean plate,
 *   which is the failure mode the silent skip already had.
 * - It renders on a zero-read run too. That is the run where an operator most
 *   needs to know whether the reads went somewhere else, so
 *   `AnalyzeStepView` mounts it in the `zeroResult` branch as well as the
 *   normal review.
 *
 * Nothing here judges. A stray count is a measurement; whether it means index
 * hopping, a splash, or an undeclared well is not decidable from the number,
 * so the panel hands the operator the wells and the reason and stops.
 */

import { FlaskConical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import {
  CONTAMINATION_SIGNAL_NAMES,
  type ContaminationSignal,
  type ContaminationSignalName,
} from "@/types/mame/models";

/** How many wells to name in a row before the count takes over. */
const NAMED_WELL_LIMIT = 6;

/** Signals whose value is a 0..1 fraction rather than a read count. */
const RATE_SIGNALS: ReadonlySet<string> = new Set(["ambiguity_rate", "chimera_rate"]);

/** Takes the number, never the signal: there is no `value ?? 0` to reach for. */
function formatValue(name: ContaminationSignalName, value: number): string {
  if (RATE_SIGNALS.has(name)) return `${(value * 100).toFixed(2)}%`;
  if (name === "plate_yield_skew") return value.toFixed(2);
  if (name === "leak_well_sharing") return String(Math.round(value));
  return value.toLocaleString();
}

function SignalRow({
  name,
  signal,
}: {
  name: ContaminationSignalName;
  /**
   * `undefined` when the report on hand carries no such signal at all. That is
   * a restored result file: `useAutosaveHydration.restoreMameResult` puts the
   * `contamination` block from disk into the store as-is, and a file written by
   * a build whose signal set differed has a hole here. It is the same "no
   * measurement" the panel already draws, so it draws it rather than
   * dereferencing its way to a blank screen.
   */
  signal: ContaminationSignal | undefined;
}) {
  const { t } = useTranslation();
  // A measurement is a state of `ok` AND a number. Anything else, including an
  // `ok` with no value, is not one: see the file header for why 0 is not an
  // option here. Held as `number | null` so the number itself is what the
  // branches below test, leaving no reading path that could substitute one.
  const value =
    signal?.state === "ok" && typeof signal.value === "number" ? signal.value : null;
  const named = (signal?.wells ?? []).slice(0, NAMED_WELL_LIMIT);
  const remaining = (signal?.wells ?? []).length - named.length;

  return (
    <div
      data-testid={`contamination-signal-${name}`}
      data-state={signal?.state ?? "missing"}
      className="flex flex-col gap-0.5 border-t border-border/60 py-1.5 first:border-t-0 first:pt-0"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 break-words text-caption font-medium text-foreground">
          {t(`mame.qc.contamination.signal.${name}`)}
        </span>
        <span
          className={`flex-shrink-0 text-caption tabular-nums ${
            value !== null ? "text-foreground" : "text-muted-foreground"
          }`}
        >
          {/* An unavailable signal shows a dash, never 0: see the file header. */}
          {value !== null
            ? formatValue(name, value)
            : t("mame.qc.contamination.notMeasured")}
        </span>
      </div>
      {value === null ? (
        <p className="text-caption text-muted-foreground">
          {signal?.reason ?? t("mame.qc.contamination.signalAbsent")}
        </p>
      ) : null}
      {value !== null && signal?.label ? (
        <p className="text-caption text-muted-foreground">
          {t(`mame.qc.contamination.sharing.${signal.label}`)}
        </p>
      ) : null}
      {value !== null && named.length > 0 ? (
        <p className="break-words text-caption text-muted-foreground">
          {t("mame.qc.contamination.wellList", {
            list: named.map((w) => `${w.well} (${w.reads.toLocaleString()})`).join(", "),
          })}
          {remaining > 0 ? ` ${t("mame.qc.contamination.more", { count: remaining })}` : ""}
        </p>
      ) : null}
    </div>
  );
}

export function ContaminationPanel() {
  const { t } = useTranslation();
  const contamination = useMameAppStore((s) => s.contamination);

  // null covers both "no run" and "a run that could not measure this" (a
  // consensus-dir run never demuxes). Neither is a clean plate, and neither has
  // a panel to draw.
  if (contamination === null) return null;

  return (
    <section
      data-testid="contamination-panel"
      data-occupancy-source={contamination.occupancy_source}
      data-replicates={contamination.replicates}
      aria-label={t("mame.qc.contamination.title")}
      className="mt-3 rounded-control border border-border bg-muted/30 px-3 py-2"
    >
      <header className="flex items-start gap-2">
        <FlaskConical size={14} className="mt-0.5 flex-shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <h3 className="text-caption font-semibold text-foreground">
            {t("mame.qc.contamination.title")}
          </h3>
          <p className="break-words text-caption text-muted-foreground">
            {t("mame.qc.contamination.subtitle", {
              wells: contamination.occupied_wells,
              source: t(`mame.qc.contamination.source.${contamination.occupancy_source}`),
            })}
          </p>
        </div>
      </header>
      <div className="mt-1.5">
        {/* The index type promises a signal per name; a report restored from
            disk need not keep that promise, so SignalRow takes `undefined`. */}
        {CONTAMINATION_SIGNAL_NAMES.map((name) => (
          <SignalRow key={name} name={name} signal={contamination.signals[name]} />
        ))}
      </div>
    </section>
  );
}
