/**
 * VerdictDetailInspector, per-well verdict detail for the MAME review screen.
 *
 * Single detail surface for BOTH entry points:
 *   - verdict table `mutant_id` button (VerdictTable)
 *   - plate map well button (WellPlate via PlateView)
 * Both write the same `selectedWell` store field, so the two views stay in sync
 * and the plate highlight follows a table click for free.
 *
 * `selectedWell` (WellEntry) carries only the plate-map subset, so the full
 * evidence comes from the verdict record looked up by the
 * (native_barcode, custom_barcode) pair, custom_barcode alone cannot tell the
 * replicate copies apart.
 *
 * Every field rendered here is already serialized per verdict by the sidecar
 * (`python-core/sidecar_mame/handlers/analyze.py::_serialize_verdict` /
 * `_serialize_replicate`). Nothing is derived that the backend did not report:
 * a missing value (null) drops its row entirely rather than being shown as 0
 * or "-", so an absent measurement never reads as a measured zero.
 */

import { useState, type ReactNode } from "react";
import { AlertTriangle, Copy, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { VerdictBadge } from "@/components/mame/widgets/VerdictBadge";
import { InfoPopover } from "@/components/ui/InfoPopover";
import { nbLabel, nbOrderKey } from "@/lib/mame/nbLabel";
import type {
  CompareParams,
  ReplicateResult,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";
import { cn } from "@/lib/utils";

/** `t` as this file uses it: a key plus optional interpolation, in and a string out. */
type TFunc = ReturnType<typeof useTranslation>["t"];

/** Key of a well: the replicate copies share a custom_barcode, so both parts matter. */
function wellKey(nativeBarcode: string, customBarcode: string): string {
  return `${nativeBarcode}|${customBarcode}`;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-3 first:mt-0">
      <h4 className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h4>
      <div className="mt-1">{children}</div>
    </section>
  );
}

/**
 * KV row. Renders nothing when the backend reported no value for the field.
 *
 * Pass `info` to turn the label into a popup trigger: the number alone does not
 * say what was counted or what it was judged against, and a `title=` tooltip
 * cannot hold that (it waits a second, never opens from the keyboard, and
 * clips at the viewport edge). Rows without `info` keep the plain span.
 */
function MetricRow({
  label,
  value,
  title,
  info,
  infoAriaLabel,
  infoTestId,
}: {
  label: string;
  value: string | number | null | undefined;
  title?: string;
  info?: ReactNode;
  infoAriaLabel?: string;
  infoTestId?: string;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-2 border-b border-border/50 py-1 last:border-0">
      {info ? (
        <InfoPopover
          label={label}
          ariaLabel={infoAriaLabel ?? label}
          testId={infoTestId}
          className="shrink-0 text-caption text-muted-foreground"
        >
          {info}
        </InfoPopover>
      ) : (
        <span className="shrink-0 text-caption text-muted-foreground" title={title}>
          {label}
        </span>
      )}
      <span className="min-w-0 break-all text-right text-caption font-medium tabular-nums text-foreground">
        {value}
      </span>
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard can be denied (permission / non-secure context). Staying
      // silent is fine: the value itself is still on screen or in the payload.
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      aria-label={label}
      title={label}
      className="inline-flex h-6 shrink-0 items-center gap-1 rounded-control border border-border/70 px-1.5 text-caption text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
    >
      {copied ? (
        <Check size={11} aria-hidden="true" />
      ) : (
        <Copy size={11} aria-hidden="true" />
      )}
      <span>{copied ? t("mame.verdictDetail.copied") : t("mame.verdictDetail.copy")}</span>
    </button>
  );
}

function percent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

/** Replicate comparison: every plate copy of this mutant side by side. */
function ReplicateComparison({
  replicate,
  currentKey,
}: {
  replicate: ReplicateResult;
  currentKey: string;
}) {
  const { t } = useTranslation();
  const wells = useMameAppStore((s) => s.wells);
  const setSelectedWell = useMameAppStore((s) => s.setSelectedWell);
  const plates = Object.entries(replicate.plate_verdicts).sort(
    ([a], [b]) => nbOrderKey(a) - nbOrderKey(b) || a.localeCompare(b),
  );
  if (plates.length === 0) return null;

  // Select a plate copy, exactly as clicking its well on the plate map or its
  // row in the verdict table does: one `selectedWell` field drives all three,
  // so the map highlight and the table follow this click for free.
  //
  // The store lookup can miss and the literal below is the answer, not padding:
  // `loadPlateData` clears `wells` to [] whenever `get_plate_data` fails
  // (analysisSlice.ts), and the inspector still has the full verdict record in
  // hand. `selected` restates the plate map's own rule (a selected replicate
  // that did not fail) against this one replicate.
  function openPlateCopy(plate: string, record: VerdictRecord): void {
    const match = wells.find(
      (w) => w.native_barcode === plate && w.barcode === record.custom_barcode,
    );
    const entry: WellEntry = match ?? {
      well: record.custom_barcode,
      barcode: record.custom_barcode,
      native_barcode: plate,
      verdict: record.verdict,
      mutant_id: record.mutant_id,
      selected: replicate.selected_plate === plate && !replicate.failed,
      notes: record.verdict_notes,
      is_fallback: replicate.is_fallback,
      fallback_reason: replicate.fallback_reason,
    };
    setSelectedWell(entry);
  }

  return (
    <Section title={t("mame.verdictDetail.sectionReplicates")}>
      <ul className="space-y-1.5">
        {plates.map(([plate, record]) => {
          const isSelected = replicate.selected_plate === plate;
          const isCurrent = wellKey(plate, record.custom_barcode) === currentKey;
          return (
            <li key={plate} data-testid="replicate-row">
              {/*
                The button is inside the li rather than the li being clickable,
                so the control is a real button for the keyboard and for
                assistive tech. The current row stays enabled: re-clicking it is
                a no-op that keeps the panel where it is, and a disabled row
                would drop out of the tab order mid-list. `aria-current` is what
                marks it instead.
              */}
              <button
                type="button"
                onClick={() => openPlateCopy(plate, record)}
                aria-current={isCurrent ? "true" : undefined}
                aria-label={t("mame.verdictDetail.replicateRowAriaLabel", {
                  plate: nbLabel(plate),
                  well: record.custom_barcode,
                })}
                title={t("mame.verdictDetail.replicateRowTitle")}
                className={cn(
                  "block w-full rounded-control border px-2 py-1.5 text-left transition-colors",
                  "hover:border-primary/50 hover:bg-muted/50",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                  isSelected ? "border-primary/40 bg-primary/5" : "border-border/70",
                  isCurrent && "ring-1 ring-ring",
                )}
              >
                <span className="flex items-center justify-between gap-1.5">
                  <span className="text-caption font-semibold text-foreground">
                    {nbLabel(plate)}
                  </span>
                  <VerdictBadge verdict={record.verdict} />
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-1">
                  <span className="rounded-full border border-border/70 bg-muted px-1.5 py-0.5 text-caption text-muted-foreground">
                    {record.custom_barcode}
                  </span>
                  {isSelected && (
                    <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-caption font-medium text-primary">
                      {t("mame.verdictDetail.selectedPlateBadge")}
                    </span>
                  )}
                  {isCurrent && (
                    <span className="rounded-full border border-border bg-background px-1.5 py-0.5 text-caption text-muted-foreground">
                      {t("mame.verdictDetail.currentWellBadge")}
                    </span>
                  )}
                </span>
                {/* How much sequence each copy is built on. Without it a
                    disagreement between two plates reads as a biological
                    difference, when it is as often one copy being ten times
                    shallower than the other. Both counts come from the same
                    serialized verdict as everything else here, and a null drops
                    its half rather than printing a zero that was never measured. */}
                {(record.read_count !== null || record.n_aligned_reads !== null) && (
                  <span
                    data-testid="replicate-depth"
                    className="mt-1 block font-mono text-caption tabular-nums text-muted-foreground"
                  >
                    {record.read_count !== null && (
                      <span title={t("mame.verdictDetail.labelReadCount")}>
                        {t("mame.verdictDetail.replicateReads", {
                          reads: record.read_count.toLocaleString(),
                        })}
                      </span>
                    )}
                    {record.n_aligned_reads !== null && (
                      <span title={t("mame.verdictDetail.labelAlignedReads")}>
                        {record.read_count !== null ? " · " : ""}
                        {t("mame.verdictDetail.replicateAligned", {
                          aligned: record.n_aligned_reads.toLocaleString(),
                        })}
                      </span>
                    )}
                  </span>
                )}
                {record.observed_aa_changes.length > 0 && (
                  <span className="mt-1 block break-all font-mono text-caption text-muted-foreground">
                    {record.observed_aa_changes.join(", ")}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-1.5">
        <MetricRow
          label={t("mame.verdictDetail.labelSelectionReason")}
          value={replicate.selection_reason}
        />
        {replicate.selected_plate === null && (
          <p className="py-1 text-caption text-muted-foreground">
            {t("mame.verdictDetail.noSelectedPlate")}
          </p>
        )}
      </div>

      {replicate.is_fallback && (
        <div
          className="mt-1.5 flex items-start gap-1.5 rounded-control border border-warning/40 bg-warning/10 px-2 py-1.5"
          role="note"
        >
          <AlertTriangle size={12} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-caption font-semibold text-warning">
              {t("mame.verdictDetail.fallbackTitle")}
            </p>
            {replicate.fallback_reason && (
              <p className="break-words text-caption text-muted-foreground">
                {replicate.fallback_reason}
              </p>
            )}
          </div>
        </div>
      )}
    </Section>
  );
}

export function VerdictDetailInspector() {
  const { t } = useTranslation();
  const selectedWell = useMameAppStore((s) => s.selectedWell);
  const verdicts = useMameAppStore((s) => s.verdicts);
  const replicates = useMameAppStore((s) => s.replicates);

  if (!selectedWell) {
    return (
      <p className="py-2 text-xs text-muted-foreground">
        {t("mame.qc.plate.inspectorNoWellSelected")}
      </p>
    );
  }

  const currentKey = wellKey(selectedWell.native_barcode, selectedWell.barcode);
  const record: VerdictRecord | null =
    verdicts.find(
      (v) => wellKey(v.native_barcode, v.custom_barcode) === currentKey,
    ) ?? null;

  const mutantId = record?.mutant_id || selectedWell.mutant_id;
  const replicate =
    mutantId !== ""
      ? (replicates.find((r) => r.mutant_id === mutantId) ?? null)
      : null;

  return (
    <div className="overflow-x-hidden" data-testid="verdict-detail">
      <WellHeader well={selectedWell} mutantId={mutantId} />

      {record ? (
        <>
          <EvidenceSection record={record} />
          {replicate && (
            <ReplicateComparison replicate={replicate} currentKey={currentKey} />
          )}
          <ConfidenceSection record={record} />
          <CoverageSection record={record} />
          {record.observed_nt_changes.length > 0 && (
            <Section title={t("mame.verdictDetail.sectionNtChanges")}>
              <p className="break-all font-mono text-caption text-foreground">
                {record.observed_nt_changes.join(", ")}
              </p>
            </Section>
          )}
          <SourceSection record={record} />
        </>
      ) : (
        <>
          <p className="mt-3 text-caption text-muted-foreground">
            {t("mame.verdictDetail.noVerdictRecord")}
          </p>
          {replicate && (
            <ReplicateComparison replicate={replicate} currentKey={currentKey} />
          )}
        </>
      )}
    </div>
  );
}

function WellHeader({ well, mutantId }: { well: WellEntry; mutantId: string }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-control border border-border bg-muted/20 px-2.5 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-caption font-medium uppercase tracking-wide text-muted-foreground">
            {t("mame.verdictDetail.wellLabel")}
          </p>
          <p className="break-all font-display text-lg font-semibold leading-none text-foreground">
            {well.well}
          </p>
        </div>
        <VerdictBadge verdict={well.verdict} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
          {nbLabel(well.native_barcode)}
        </span>
        <span className="rounded-full border border-border/70 bg-muted px-2 py-0.5 text-caption font-medium text-muted-foreground">
          {well.barcode}
        </span>
        {mutantId !== "" && (
          <span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary">
            {mutantId}
          </span>
        )}
      </div>
    </div>
  );
}

/** Priority 1: expected vs observed, side by side. */
function EvidenceSection({ record }: { record: VerdictRecord }) {
  const { t } = useTranslation();
  const observed = record.observed_aa_changes;
  return (
    <Section title={t("mame.verdictDetail.sectionEvidence")}>
      <div className="grid grid-cols-2 gap-2">
        <div className="min-w-0">
          <p className="text-caption text-muted-foreground">
            {t("mame.verdictDetail.labelExpected")}
          </p>
          {record.expected_mutations.length > 0 ? (
            <p className="break-all font-mono text-caption font-medium text-foreground">
              {record.expected_mutations.join(", ")}
            </p>
          ) : (
            <p className="text-caption text-muted-foreground">
              {t("mame.verdictDetail.expectedNone")}
            </p>
          )}
        </div>
        <div className="min-w-0">
          <p className="text-caption text-muted-foreground">
            {t("mame.verdictDetail.labelObserved")}
          </p>
          {observed.length > 0 ? (
            <p className="break-all font-mono text-caption font-medium text-foreground">
              {observed.join(", ")}
            </p>
          ) : (
            <p className="text-caption font-medium text-warning">
              {t("mame.verdictDetail.observedNone")}
            </p>
          )}
        </div>
      </div>
      <div className="mt-1.5">
        <MetricRow
          label={t("mame.verdictDetail.labelVerdictNotes")}
          value={record.verdict_notes}
        />
        <MetricRow
          label={t("mame.verdictDetail.labelNoCallAa")}
          value={record.n_no_call_aa > 0 ? record.n_no_call_aa : null}
          title={t("mame.verdictDetail.labelNoCallAaHelp")}
        />
      </div>
    </Section>
  );
}

/**
 * The ten Confidence metrics, each with the three things a reader needs before
 * the number means anything: what was counted, at which stage, and whether it
 * can move the verdict. Seven of the ten are diagnostic and move nothing; their
 * `effect` copy says so plainly rather than leaving the reader to guess.
 *
 * A `Record` keyed by the metric union (not a lookup by template literal) so
 * the type checker fails a metric added here without copy, and so every key is
 * a literal string that greps.
 */
type MetricKey =
  | "readCount"
  | "inputReads"
  | "alignedReads"
  | "mapqFailed"
  | "spanFailed"
  | "mixedPositions"
  | "maxMinorAllele"
  | "lowDepthPositions"
  | "consensusN"
  | "lowQualityBases";

interface MetricCopy {
  /** Row label, reused as the popup heading. */
  label: string;
  what: string;
  stage: string;
  effect: string;
}

const METRIC_COPY: Record<MetricKey, MetricCopy> = {
  readCount: {
    label: "mame.verdictDetail.labelReadCount",
    what: "mame.verdictDetail.metricInfo.readCount.what",
    stage: "mame.verdictDetail.metricInfo.readCount.stage",
    effect: "mame.verdictDetail.metricInfo.readCount.effect",
  },
  inputReads: {
    label: "mame.verdictDetail.labelInputReads",
    what: "mame.verdictDetail.metricInfo.inputReads.what",
    stage: "mame.verdictDetail.metricInfo.inputReads.stage",
    effect: "mame.verdictDetail.metricInfo.inputReads.effect",
  },
  alignedReads: {
    label: "mame.verdictDetail.labelAlignedReads",
    what: "mame.verdictDetail.metricInfo.alignedReads.what",
    stage: "mame.verdictDetail.metricInfo.alignedReads.stage",
    effect: "mame.verdictDetail.metricInfo.alignedReads.effect",
  },
  mapqFailed: {
    label: "mame.verdictDetail.labelMapqFailed",
    what: "mame.verdictDetail.metricInfo.mapqFailed.what",
    stage: "mame.verdictDetail.metricInfo.mapqFailed.stage",
    effect: "mame.verdictDetail.metricInfo.mapqFailed.effect",
  },
  spanFailed: {
    label: "mame.verdictDetail.labelSpanFailed",
    what: "mame.verdictDetail.metricInfo.spanFailed.what",
    stage: "mame.verdictDetail.metricInfo.spanFailed.stage",
    effect: "mame.verdictDetail.metricInfo.spanFailed.effect",
  },
  mixedPositions: {
    label: "mame.verdictDetail.labelMixedPositions",
    what: "mame.verdictDetail.metricInfo.mixedPositions.what",
    stage: "mame.verdictDetail.metricInfo.mixedPositions.stage",
    effect: "mame.verdictDetail.metricInfo.mixedPositions.effect",
  },
  maxMinorAllele: {
    label: "mame.verdictDetail.labelMaxMinorAllele",
    what: "mame.verdictDetail.metricInfo.maxMinorAllele.what",
    stage: "mame.verdictDetail.metricInfo.maxMinorAllele.stage",
    effect: "mame.verdictDetail.metricInfo.maxMinorAllele.effect",
  },
  lowDepthPositions: {
    label: "mame.verdictDetail.labelLowDepthPositions",
    what: "mame.verdictDetail.metricInfo.lowDepthPositions.what",
    stage: "mame.verdictDetail.metricInfo.lowDepthPositions.stage",
    effect: "mame.verdictDetail.metricInfo.lowDepthPositions.effect",
  },
  consensusN: {
    label: "mame.verdictDetail.labelConsensusN",
    what: "mame.verdictDetail.metricInfo.consensusN.what",
    stage: "mame.verdictDetail.metricInfo.consensusN.stage",
    effect: "mame.verdictDetail.metricInfo.consensusN.effect",
  },
  lowQualityBases: {
    label: "mame.verdictDetail.labelLowQualityBases",
    what: "mame.verdictDetail.metricInfo.lowQualityBases.what",
    stage: "mame.verdictDetail.metricInfo.lowQualityBases.stage",
    effect: "mame.verdictDetail.metricInfo.lowQualityBases.effect",
  },
};

/**
 * What this run judged the metric against, from the run's own reported
 * thresholds. Empty for a metric no threshold governs.
 *
 * `compareParams` is null for a result restored from a snapshot written before
 * the sidecar reported its thresholds, and the answer there is to say they are
 * unknown. Substituting a literal would keep reading as correct long after the
 * backend default moved, and `min_read_count` is exactly that case: the store
 * never sends one, so the number in force is the backend's, not the operator's.
 */
function thresholdLines(
  metric: MetricKey,
  compareParams: CompareParams | null,
  t: TFunc,
): string[] {
  const unknown = [t("mame.verdictDetail.metricInfo.thresholdUnknown")];
  switch (metric) {
    case "readCount": {
      if (!compareParams) return unknown;
      return [
        compareParams.min_read_count === null
          ? t("mame.verdictDetail.metricInfo.readCount.thresholdDepthOff")
          : t("mame.verdictDetail.metricInfo.readCount.thresholdDepth", {
              count: compareParams.min_read_count,
            }),
        compareParams.mixed_confident_read_count === null
          ? t("mame.verdictDetail.metricInfo.readCount.thresholdMixedOff")
          : t("mame.verdictDetail.metricInfo.readCount.thresholdMixed", {
              count: compareParams.mixed_confident_read_count,
              factor: compareParams.mixed_confident_depth_factor,
            }),
        t("mame.verdictDetail.metricInfo.readCount.thresholdFileSize", {
          size: compareParams.min_file_size_kb,
        }),
      ];
    }
    case "mixedPositions": {
      if (!compareParams) return unknown;
      return [
        compareParams.mixed_confident_read_count === null
          ? t("mame.verdictDetail.metricInfo.mixedPositions.thresholdDepthOff")
          : t("mame.verdictDetail.metricInfo.mixedPositions.thresholdDepth", {
              count: compareParams.mixed_confident_read_count,
            }),
      ];
    }
    case "consensusN": {
      if (!compareParams) return unknown;
      return [
        compareParams.max_consensus_n_fraction === null
          ? t("mame.verdictDetail.metricInfo.consensusN.thresholdOff")
          : t("mame.verdictDetail.metricInfo.consensusN.threshold", {
              value: percent(compareParams.max_consensus_n_fraction),
            }),
      ];
    }
    default:
      return [];
  }
}

/**
 * The other number this one has to be read next to. Only the max minor allele
 * fraction has one: it is a maximum over positions and no threshold judges it,
 * so 4% is a clean well when ordinary positions sit at 3% and a contaminated
 * one when they sit at 0.2%. The median is that floor.
 */
function contextLines(metric: MetricKey, record: VerdictRecord, t: TFunc): string[] {
  if (metric !== "maxMinorAllele") return [];
  return [
    record.median_minor_allele_fraction === undefined
      ? t("mame.verdictDetail.metricInfo.maxMinorAllele.noiseFloorUnknown")
      : t("mame.verdictDetail.metricInfo.maxMinorAllele.noiseFloor", {
          value: percent(record.median_minor_allele_fraction),
        }),
  ];
}

/**
 * Why the number in front of the reader may not mean what it looks like.
 *
 * The three states of `consensus_n_fraction_evaluable` stay three: `false` is a
 * consensus whose N fraction could not be recovered, so 0.0 was substituted and
 * the NO_CALL gate was skipped; `undefined` is a result saved before the flag
 * existed, so whether the gate ran is simply unknown. Collapsing either into
 * "clean" reports an unmeasurable well as a measured one.
 */
function caveatLines(metric: MetricKey, record: VerdictRecord, t: TFunc): string[] {
  if (metric !== "consensusN") return [];
  if (record.consensus_n_fraction_evaluable === false) {
    return [t("mame.verdictDetail.metricInfo.consensusN.notEvaluable")];
  }
  if (record.consensus_n_fraction_evaluable === undefined) {
    return [t("mame.verdictDetail.metricInfo.consensusN.evaluableUnknown")];
  }
  return [];
}

function InfoBlock({ label, lines }: { label: string; lines: string[] }) {
  return (
    <div>
      <p className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      {lines.map((line) => (
        <p key={line} className="text-popover-foreground">
          {line}
        </p>
      ))}
    </div>
  );
}

/** Popup body for one Confidence metric. */
function MetricInfo({
  metric,
  record,
  compareParams,
}: {
  metric: MetricKey;
  record: VerdictRecord;
  compareParams: CompareParams | null;
}) {
  const { t } = useTranslation();
  const copy = METRIC_COPY[metric];
  const thresholds = thresholdLines(metric, compareParams, t);
  const context = contextLines(metric, record, t);
  const caveats = caveatLines(metric, record, t);
  return (
    <div className="space-y-2">
      <InfoBlock
        label={t("mame.verdictDetail.metricInfo.whatLabel")}
        lines={[t(copy.what)]}
      />
      <InfoBlock
        label={t("mame.verdictDetail.metricInfo.stageLabel")}
        lines={[t(copy.stage)]}
      />
      <InfoBlock
        label={t("mame.verdictDetail.metricInfo.effectLabel")}
        lines={[t(copy.effect)]}
      />
      {thresholds.length > 0 && (
        <InfoBlock
          label={t("mame.verdictDetail.metricInfo.thresholdLabel")}
          lines={thresholds}
        />
      )}
      {context.length > 0 && (
        <InfoBlock
          label={t("mame.verdictDetail.metricInfo.contextLabel")}
          lines={context}
        />
      )}
      {caveats.map((line) => (
        <p key={line} className="font-medium text-warning">
          {line}
        </p>
      ))}
    </div>
  );
}

/** Priority 3: "can this PASS be trusted?" counters. */
function ConfidenceSection({ record }: { record: VerdictRecord }) {
  const { t } = useTranslation();
  // The thresholds the run that produced this record judged it against, never
  // the current input fields: an operator may have changed those since, and
  // min_read_count has no input field at all.
  const compareParams = useMameAppStore((s) => s.compareParams);

  function row(metric: MetricKey, value: string | number | null) {
    const label = t(METRIC_COPY[metric].label);
    return (
      <MetricRow
        label={label}
        value={value}
        info={
          <MetricInfo metric={metric} record={record} compareParams={compareParams} />
        }
        infoAriaLabel={t("mame.verdictDetail.metricInfo.openAria", { metric: label })}
        infoTestId={`metric-info-${metric}`}
      />
    );
  }

  return (
    <Section title={t("mame.verdictDetail.sectionConfidence")}>
      {row("readCount", record.read_count?.toLocaleString() ?? null)}
      {row("inputReads", record.n_input_reads?.toLocaleString() ?? null)}
      {row("alignedReads", record.n_aligned_reads?.toLocaleString() ?? null)}
      {row("mapqFailed", record.n_mapq_failed)}
      {row("spanFailed", record.n_span_failed)}
      {row("mixedPositions", record.n_mixed_positions)}
      {row("maxMinorAllele", percent(record.max_minor_allele_fraction))}
      {row("lowDepthPositions", record.n_low_depth_positions)}
      {row("consensusN", percent(record.consensus_n_fraction))}
      {row("lowQualityBases", record.n_low_quality_bases)}
    </Section>
  );
}

/**
 * Coverage uniformity and consensus identity for this well.
 *
 * A well covered evenly at 100x and one averaging 100x with a 200 bp hole report
 * the same read count; these five say which one it was. None of them gates a
 * verdict (models.ts: "Reported only; no verdict, gate or severity rule reads
 * any of them"), so nothing here is coloured or badged.
 *
 * `null` and `undefined` both mean NOT MEASURED and are printed as such rather
 * than hidden, because a CV of 0 is a perfectly flat well and an identity of 0
 * is a consensus matching the reference nowhere. Both are strong readings, and
 * a blank row invites the reader to supply whichever one they expected. The
 * sidecar omits the five independently, so a well with no reads reports a real
 * `breadth_at_mix_min_depth` of 0 with the other four absent.
 *
 * `consensus_identity` never appears without `consensus_n_fraction` beside it.
 * Identity is computed over CALLED bases only, so a well whose consensus is 95%
 * N can read 100.0% identical and look perfect; the N fraction is the number
 * that says how much of the sequence that percentage was measured on.
 */
function CoverageSection({ record }: { record: VerdictRecord }) {
  const { t } = useTranslation();
  const unknown = t("mame.verdictDetail.coverage.notMeasured");
  const num = (v: number | null | undefined) =>
    typeof v === "number" ? v.toLocaleString() : unknown;
  const pct = (v: number | null | undefined) =>
    typeof v === "number" ? `${(v * 100).toFixed(1)}%` : unknown;
  const cv = (v: number | null | undefined) =>
    typeof v === "number" ? v.toFixed(2) : unknown;

  // A result saved before these existed carries none of the five. One line saying
  // so beats five rows of "not measured", the same shape ContaminationPanel uses
  // for a report that predates a signal.
  const measured =
    typeof record.depth_cv === "number" ||
    typeof record.depth_p10 === "number" ||
    typeof record.depth_min_covered === "number" ||
    typeof record.breadth_at_mix_min_depth === "number" ||
    typeof record.consensus_identity === "number";

  return (
    <Section title={t("mame.verdictDetail.sectionCoverage")}>
      <div data-testid="verdict-coverage" data-measured={String(measured)}>
        {measured ? (
          <>
            <MetricRow label={t("mame.verdictDetail.coverage.depthCv")} value={cv(record.depth_cv)} />
            <MetricRow label={t("mame.verdictDetail.coverage.depthP10")} value={num(record.depth_p10)} />
            <MetricRow
              label={t("mame.verdictDetail.coverage.depthMinCovered")}
              value={num(record.depth_min_covered)}
            />
            <MetricRow
              label={t("mame.verdictDetail.coverage.breadth")}
              value={pct(record.breadth_at_mix_min_depth)}
            />
            <MetricRow
              label={t("mame.verdictDetail.coverage.consensusIdentity")}
              value={pct(record.consensus_identity)}
            />
            {/* Directly under identity, always. See the block comment. */}
            <MetricRow
              label={t("mame.verdictDetail.coverage.consensusN")}
              value={pct(record.consensus_n_fraction)}
            />
            <p className="mt-1 text-caption text-muted-foreground">
              {t("mame.verdictDetail.coverage.identityNote")}
            </p>
            {record.consensus_n_fraction_evaluable === false && (
              <p className="mt-1 text-caption font-medium text-warning">
                {t("mame.verdictDetail.coverage.nNotEvaluable")}
              </p>
            )}
          </>
        ) : (
          <p className="text-caption text-muted-foreground">
            {t("mame.verdictDetail.coverage.absent")}
          </p>
        )}
      </div>
    </Section>
  );
}

/** Priority 5: provenance. The 561-residue aa_sequence stays behind a copy button. */
function SourceSection({ record }: { record: VerdictRecord }) {
  const { t } = useTranslation();
  if (!record.source_path && !record.aa_sequence) return null;
  return (
    <Section title={t("mame.verdictDetail.sectionSource")}>
      {record.source_path && (
        <div className="flex items-start justify-between gap-2">
          <p
            className="min-w-0 break-all font-mono text-caption text-muted-foreground"
            title={record.source_path}
          >
            {record.source_path}
          </p>
          <CopyButton
            text={record.source_path}
            label={t("mame.verdictDetail.copySourcePath")}
          />
        </div>
      )}
      {record.aa_sequence && (
        <div className="mt-1.5 flex items-center justify-between gap-2">
          <p className="min-w-0 text-caption text-muted-foreground">
            {t("mame.verdictDetail.aaSequenceLength", {
              count: record.aa_sequence.length,
            })}
          </p>
          <CopyButton
            text={record.aa_sequence}
            label={t("mame.verdictDetail.copyAaSequence")}
          />
        </div>
      )}
    </Section>
  );
}
