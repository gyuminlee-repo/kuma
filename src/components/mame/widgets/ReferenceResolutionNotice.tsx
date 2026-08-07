/**
 * ReferenceResolutionNotice, the run analysed a slice of the picked reference.
 *
 * On a MinKNOW run folder the pipeline does not use the reference file as
 * given. It finds the barcode workbook primer tails inside it and cuts the
 * amplicon out (`kuma_core/mame/ingest/amplicon_reference.py`,
 * `resolve_amplicon_reference`), writing `{stem}.amplicon.fa` beside the demux
 * output, and every verdict on screen was scored against that slice. The
 * substitution was invisible: the response has carried `reference_resolution`
 * since the handler started sending it, and no component read it, so the file
 * named in the form was not the file the run read and nothing said so.
 *
 * A statement, never a warning. Extraction is the normal and correct path for
 * a run folder: the reads are amplicon reads, and a whole-construct reference
 * would lose all of them at the coverage gate. The operator is told which
 * region was used so the number on screen can be checked against the construct
 * map, not so anything gets fixed.
 *
 * Silent in the two states that have no substitution to report, which are
 * deliberately separate guards below and separate values in the store: no
 * resolution at all (null), and a resolution that measured and cut nothing
 * (`extracted: false`).
 */

import { Scissors } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

export function ReferenceResolutionNotice() {
  const { t } = useTranslation();
  const resolution = useMameAppStore((s) => s.referenceResolution);

  // No run has reported a resolution: no run since the last reset, a run that
  // resolves no reference (only the raw-run path does), or a result persisted
  // before the sidecar sent the field. Nothing was measured, so nothing is said.
  if (resolution === null) return null;
  // A run DID resolve the reference and used the whole file unmodified. That is
  // measured, and the store keeps it distinct from the null above, but there is
  // no substitution to report: the file named in the form is the file that was
  // read, which is what the screen already shows.
  if (!resolution.extracted) return null;

  const spanStart = resolution.span_start;
  const spanEnd = resolution.span_end;
  // Type guard rather than a state. The sidecar sets `extracted` only on the
  // branch that has a span (`resolve_amplicon_reference`); every skip path
  // returns `extracted: false` with a null span. Without a span there is no
  // region to name, and naming the region is the whole point of the notice.
  if (spanStart === null || spanEnd === null) return null;

  return (
    <div
      role="status"
      data-testid="reference-resolution-notice"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/40 px-3 py-2 text-caption"
    >
      <Scissors size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className="font-semibold text-foreground">
          {t("mame.qc.referenceResolution.title")}
        </p>
        <p className="text-muted-foreground">
          {t("mame.qc.referenceResolution.desc", {
            spanStart,
            spanEnd,
            // Both bounds are inclusive 1-based positions, as the handler sends
            // them (`span.start + 1` .. `span.end`), so the length is the
            // closed-interval count.
            sliceLength: spanEnd - spanStart + 1,
            originalLength: resolution.original_length,
          })}
        </p>
        <p className="text-muted-foreground">
          {t("mame.qc.referenceResolution.normal")}
        </p>
      </div>
    </div>
  );
}
