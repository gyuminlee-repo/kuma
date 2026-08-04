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

import { useState } from "react";
import { AlertTriangle, Copy, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { VerdictBadge } from "@/components/mame/widgets/VerdictBadge";
import { nbLabel, nbOrderKey } from "@/lib/mame/nbLabel";
import type { ReplicateResult, VerdictRecord, WellEntry } from "@/types/mame/models";
import { cn } from "@/lib/utils";

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

/** KV row. Renders nothing when the backend reported no value for the field. */
function MetricRow({
  label,
  value,
  title,
}: {
  label: string;
  value: string | number | null | undefined;
  title?: string;
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-start justify-between gap-2 border-b border-border/50 py-1 last:border-0">
      <span className="shrink-0 text-caption text-muted-foreground" title={title}>
        {label}
      </span>
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
  const plates = Object.entries(replicate.plate_verdicts).sort(
    ([a], [b]) => nbOrderKey(a) - nbOrderKey(b) || a.localeCompare(b),
  );
  if (plates.length === 0) return null;

  return (
    <Section title={t("mame.verdictDetail.sectionReplicates")}>
      <ul className="space-y-1.5">
        {plates.map(([plate, record]) => {
          const isSelected = replicate.selected_plate === plate;
          const isCurrent = wellKey(plate, record.custom_barcode) === currentKey;
          return (
            <li
              key={plate}
              data-testid="replicate-row"
              className={cn(
                "rounded-control border px-2 py-1.5",
                isSelected ? "border-primary/40 bg-primary/5" : "border-border/70",
                isCurrent && "ring-1 ring-ring",
              )}
            >
              <div className="flex items-center justify-between gap-1.5">
                <span className="text-caption font-semibold text-foreground">
                  {nbLabel(plate)}
                </span>
                <VerdictBadge verdict={record.verdict} />
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1">
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
              </div>
              {record.observed_aa_changes.length > 0 && (
                <p className="mt-1 break-all font-mono text-caption text-muted-foreground">
                  {record.observed_aa_changes.join(", ")}
                </p>
              )}
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

/** Priority 3: "can this PASS be trusted?" counters. */
function ConfidenceSection({ record }: { record: VerdictRecord }) {
  const { t } = useTranslation();
  return (
    <Section title={t("mame.verdictDetail.sectionConfidence")}>
      <MetricRow
        label={t("mame.verdictDetail.labelReadCount")}
        value={record.read_count?.toLocaleString() ?? null}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelInputReads")}
        value={record.n_input_reads?.toLocaleString() ?? null}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelAlignedReads")}
        value={record.n_aligned_reads?.toLocaleString() ?? null}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelMapqFailed")}
        value={record.n_mapq_failed}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelSpanFailed")}
        value={record.n_span_failed}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelMixedPositions")}
        value={record.n_mixed_positions}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelMaxMinorAllele")}
        value={percent(record.max_minor_allele_fraction)}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelLowDepthPositions")}
        value={record.n_low_depth_positions}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelConsensusN")}
        value={percent(record.consensus_n_fraction)}
      />
      <MetricRow
        label={t("mame.verdictDetail.labelLowQualityBases")}
        value={record.n_low_quality_bases}
      />
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
