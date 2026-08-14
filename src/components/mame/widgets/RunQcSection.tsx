/**
 * RunQcSection, the collapsed QC drawer on the analyze review screen (2.2).
 *
 * The verdict table and the plate map are what an operator came to 2.2 for, so
 * everything here stays behind a disclosure that starts closed. What it holds is
 * measurement the run already produced and nothing on screen was reading:
 *
 *  - the five `RunHealthPanel` sections other than the verdict breakdown, which
 *    2.2 already draws beside the plate. Until now `RUN_HEALTH_QC_SECTIONS` had
 *    no mount anywhere in the app, so file-size, throughput, pore yield, barcode
 *    distribution and cross-talk were computed and dropped.
 *  - `demuxResult.filter_stats`, what the quality filter threw away and why.
 *  - `run_quality.position_recurrence`, which reference positions came back well
 *    after well.
 *  - `run_quality.read_length`, the instrument's own N50 read against this run's
 *    reference.
 *
 * Three rules this file keeps:
 *
 *  - A missing measurement states its REASON. "No data" and 0 are different
 *    readings and one must never be drawn as the other. Inherited from
 *    `ContaminationPanel`, whose header says why.
 *  - Nothing here grades. `run_quality.ts` says so of every field it carries
 *    (`enforced: false` throughout, "no cut between the two survives a second
 *    run"), so there are no severity colours and no threshold badges. The
 *    concatemer reading of a high N50 ratio is stated as help copy that is
 *    always present, never as a conditional warning: a badge that appears above
 *    some value IS the cut the block refuses to make.
 *  - Every count that could be absent goes through `numText`/`pctText`/
 *    `ratioText`. There is no `?? 0` and no `||` on a measurement in this file.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AdvancedSection } from "@/components/ui/AdvancedSection";
import {
  RUN_HEALTH_QC_SECTIONS,
  RunHealthPanel,
} from "@/components/mame/widgets/RunHealthPanel";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { RunHealthData } from "@/types/mame/models";

/** A block heading plus either its content or the reason it has none. */
export function QcBlock({
  testId,
  title,
  reason,
  children,
}: {
  testId: string;
  title: string;
  /** Set when the measurement is absent. Rendered instead of `children`. */
  reason?: string;
  children?: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      data-state={reason === undefined ? "present" : "unavailable"}
      className="border-t border-border/60 pt-2 first:border-t-0 first:pt-0"
    >
      <h3 className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h3>
      {reason === undefined ? (
        <div className="mt-1.5">{children}</div>
      ) : (
        <p className="mt-1 text-caption text-muted-foreground">{reason}</p>
      )}
    </section>
  );
}

/** One label/value line. The value is already formatted, absences included. */
function QcRow({
  testId,
  label,
  value,
}: {
  testId: string;
  label: string;
  value: string;
}) {
  return (
    <div
      data-testid={testId}
      className="flex items-baseline justify-between gap-3 border-t border-border/40 py-0.5 first:border-t-0"
    >
      <span className="min-w-0 break-words text-caption text-muted-foreground">{label}</span>
      <span className="flex-shrink-0 text-caption tabular-nums text-foreground">{value}</span>
    </div>
  );
}

export function RunQcSection({ runHealth }: { runHealth: RunHealthData | null }) {
  const { t } = useTranslation();
  const demuxResult = useMameAppStore((s) => s.demuxResult);
  const runQuality = useMameAppStore((s) => s.runQuality);
  // Collapsed by default: the disclosure exists so that the table and the plate
  // keep the screen. AdvancedSection is controlled and renders children only
  // while open.
  const [open, setOpen] = useState(false);

  const unknown = t("mame.runHealth.qcNotMeasured");
  /** A count. Absent is the localized unknown, never 0. */
  const numText = (v: number | null | undefined): string =>
    typeof v === "number" ? v.toLocaleString() : unknown;
  /** A 0..1 fraction as a percentage. 0 is a reading and prints as 0.0%. */
  const pctText = (v: number | null | undefined): string =>
    typeof v === "number" ? `${(v * 100).toFixed(1)}%` : unknown;
  const ratioText = (v: number | null | undefined): string =>
    typeof v === "number" ? v.toFixed(2) : unknown;

  // Two distinct absences. A consensus-directory run never demuxes at all; a raw
  // run that was handed no sequencing_summary demuxes and cannot fill the filter
  // tally (handlers/demux.py). Saying "no data" to both hides which happened.
  const filterStats = demuxResult?.filter_stats ?? null;
  const filterReason =
    demuxResult === null
      ? t("mame.runHealth.filterStats.noDemux")
      : filterStats === null
        ? t("mame.runHealth.filterStats.noSummary")
        : undefined;

  // Three states, not two. `undefined` on a present run_quality is a result
  // saved by a sidecar older than the tally, which run_quality.ts says must not
  // read as a plate on which nothing recurred.
  const recurrence = runQuality?.position_recurrence;
  const recurrenceReason =
    runQuality === null
      ? t("mame.runQuality.positionRecurrence.noRun")
      : recurrence === undefined
        ? t("mame.runQuality.positionRecurrence.predatesBuild")
        : undefined;

  const readLength = runQuality?.read_length;
  const readLengthReason =
    runQuality === null
      ? t("mame.runQuality.readLength.noRun")
      : readLength === undefined
        ? t("mame.runQuality.readLength.predatesBuild")
        : readLength.histograms === null
          ? t("mame.runQuality.readLength.notRead")
          : undefined;

  return (
    <div className="mt-3">
      <AdvancedSection
        title={t("mame.runHealth.qcSectionTitle")}
        ariaLabel={t("mame.runHealth.qcSectionAriaLabel")}
        id="mame-run-qc-panel"
        open={open}
        onToggle={() => setOpen((v) => !v)}
      >
        <div data-testid="run-qc-section" className="flex flex-col gap-3">
          <QcBlock
            testId="run-qc-health"
            title={t("mame.runHealth.qcHealthTitle")}
            reason={runHealth === null ? t("mame.runHealth.qcHealthAbsent") : undefined}
          >
            {runHealth !== null && (
              <RunHealthPanel
                health={runHealth}
                sections={RUN_HEALTH_QC_SECTIONS}
                className="p-0"
              />
            )}
          </QcBlock>

          <QcBlock
            testId="run-qc-filter-stats"
            title={t("mame.runHealth.filterStats.title")}
            reason={filterReason}
          >
            {filterStats !== null && (
              <div>
                <QcRow
                  testId="filter-stat-input"
                  label={t("mame.runHealth.filterStats.input")}
                  value={numText(filterStats.n_input)}
                />
                <QcRow
                  testId="filter-stat-passed"
                  label={t("mame.runHealth.filterStats.passed")}
                  value={numText(filterStats.n_passed)}
                />
                <QcRow
                  testId="filter-stat-qscore"
                  label={t("mame.runHealth.filterStats.failedQscore")}
                  value={numText(filterStats.n_failed_qscore)}
                />
                <QcRow
                  testId="filter-stat-length"
                  label={t("mame.runHealth.filterStats.failedLength")}
                  value={numText(filterStats.n_failed_length)}
                />
                <QcRow
                  testId="filter-stat-barcode"
                  label={t("mame.runHealth.filterStats.failedBarcode")}
                  value={numText(filterStats.n_failed_barcode)}
                />
              </div>
            )}
          </QcBlock>

          <QcBlock
            testId="run-qc-position-recurrence"
            title={t("mame.runQuality.positionRecurrence.title")}
            reason={recurrenceReason}
          >
            {recurrence !== undefined && (
              <div className="flex flex-col gap-1.5">
                <p className="text-caption text-muted-foreground">
                  {t("mame.runQuality.positionRecurrence.what")}
                </p>
                {/* `lower_bound` is always true on this block, so the sentence is
                    unconditional. Each well contributes at most ten ranked
                    positions, so an eleventh is simply missing from the tally,
                    and wells_truncated is how many wells hit that ceiling. */}
                <p
                  data-testid="recurrence-lower-bound"
                  data-lower-bound={String(recurrence.lower_bound)}
                  className="text-caption text-muted-foreground"
                >
                  {t("mame.runQuality.positionRecurrence.lowerBound", {
                    truncated: recurrence.wells_truncated,
                    contributing: recurrence.wells_contributing,
                  })}
                </p>
                <div>
                  <QcRow
                    testId="recurrence-contributing"
                    label={t("mame.runQuality.positionRecurrence.wellsContributing")}
                    value={numText(recurrence.wells_contributing)}
                  />
                  <QcRow
                    testId="recurrence-truncated"
                    label={t("mame.runQuality.positionRecurrence.wellsTruncated")}
                    value={numText(recurrence.wells_truncated)}
                  />
                  <QcRow
                    testId="recurrence-seen"
                    label={t("mame.runQuality.positionRecurrence.positionsSeen")}
                    value={numText(recurrence.positions_seen)}
                  />
                  <QcRow
                    testId="recurrence-single"
                    label={t("mame.runQuality.positionRecurrence.positionsSingleWell")}
                    value={numText(recurrence.positions_single_well)}
                  />
                </div>
                {recurrence.positions.length === 0 ? (
                  <p className="text-caption text-muted-foreground">
                    {t("mame.runQuality.positionRecurrence.none")}
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-caption" data-testid="recurrence-table">
                      <caption className="sr-only">
                        {t("mame.runQuality.positionRecurrence.caption")}
                      </caption>
                      <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                          <th scope="col" className="py-1 pr-3 font-medium">
                            {t("mame.runQuality.positionRecurrence.colPosition")}
                          </th>
                          <th scope="col" className="py-1 pr-3 font-medium">
                            {t("mame.runQuality.positionRecurrence.colWells")}
                          </th>
                          <th scope="col" className="py-1 pr-3 font-medium">
                            {t("mame.runQuality.positionRecurrence.colMedianShare")}
                          </th>
                          <th scope="col" className="py-1 pr-3 font-medium">
                            {t("mame.runQuality.positionRecurrence.colShareRange")}
                          </th>
                          <th scope="col" className="py-1 font-medium">
                            {t("mame.runQuality.positionRecurrence.colSharesKnown")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {recurrence.positions.map((p) => (
                          <tr
                            key={p.position}
                            data-testid={`recurrence-row-${p.position}`}
                            data-share-known={String(p.median_weak_strand_share !== null)}
                            className="border-b border-border/50 last:border-0"
                          >
                            <td className="py-1 pr-3 tabular-nums">{p.position}</td>
                            <td className="py-1 pr-3 tabular-nums">{p.wells}</td>
                            {/* Null is UNKNOWN and 0.0 is the reading "one strand
                                only". They are opposite findings, so the unknown
                                never borrows the zero. */}
                            <td className="py-1 pr-3 tabular-nums">
                              {pctText(p.median_weak_strand_share)}
                            </td>
                            <td className="py-1 pr-3 tabular-nums">
                              {`${pctText(p.min_weak_strand_share)} / ${pctText(p.max_weak_strand_share)}`}
                            </td>
                            <td className="py-1 tabular-nums">
                              {`${p.shares_known} / ${p.shares_known + p.shares_unknown}`}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </QcBlock>

          <QcBlock
            testId="run-qc-read-length"
            title={t("mame.runQuality.readLength.title")}
            reason={readLengthReason}
          >
            {readLength !== undefined && readLength.histograms !== null && (
              <div className="flex flex-col gap-2">
                <p className="text-caption text-muted-foreground">
                  {readLength.reference_length_bp === null
                    ? t("mame.runQuality.readLength.referenceUnknown")
                    : t("mame.runQuality.readLength.reference", {
                        bp: readLength.reference_length_bp.toLocaleString(),
                      })}
                </p>
                {/* Unconditional, never keyed on the value. A ratio near two is
                    what a concatemer population looks like and also what a
                    deliberately long amplicon looks like; run_quality.ts refuses
                    the cut between them, so this screen refuses it too. */}
                <p className="text-caption text-muted-foreground">
                  {t("mame.runQuality.readLength.concatemerNote")}
                </p>
                {readLength.histograms.length === 0 ? (
                  <p className="text-caption text-muted-foreground">
                    {t("mame.runQuality.readLength.noEntries")}
                  </p>
                ) : (
                  readLength.histograms.map((h, i) => (
                    <div
                      key={`${h.read_length_type ?? "unlabelled"}-${i}`}
                      data-testid={`read-length-entry-${i}`}
                      className="rounded-control border border-border/60 px-2 py-1"
                    >
                      <p className="text-caption font-medium text-foreground">
                        {h.read_length_type ?? t("mame.runQuality.readLength.unlabelled")}
                      </p>
                      <QcRow
                        testId={`read-length-n50-${i}`}
                        label={t("mame.runQuality.readLength.n50")}
                        value={numText(h.n50)}
                      />
                      <QcRow
                        testId={`read-length-ratio-${i}`}
                        label={t("mame.runQuality.readLength.n50OverReference")}
                        value={ratioText(h.n50_over_reference)}
                      />
                      <QcRow
                        testId={`read-length-near-${i}`}
                        label={t("mame.runQuality.readLength.nearReferenceFraction")}
                        value={pctText(h.near_reference_bases_fraction)}
                      />
                      <QcRow
                        testId={`read-length-over2x-${i}`}
                        label={t("mame.runQuality.readLength.over2xFraction")}
                        value={pctText(h.over_2x_reference_bases_fraction)}
                      />
                    </div>
                  ))
                )}
                <p className="text-caption text-muted-foreground">
                  {t("mame.runQuality.readLength.basesNote")}
                </p>
              </div>
            )}
          </QcBlock>
        </div>
      </AdvancedSection>
    </div>
  );
}
