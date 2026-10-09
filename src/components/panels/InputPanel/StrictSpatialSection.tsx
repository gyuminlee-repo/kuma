import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { currentStrictSpatialResult } from "@/lib/strictSpatial";

const Selection3DPanel = lazy(() => import("../Selection3DPanel").then((module) => ({ default: module.Selection3DPanel })));

/** Session-only conservative selector; annotations explain the selection, never weight it. */
export function StrictSpatialSection() {
  const { t } = useTranslation();
  const enabled = useAppStore((s) => s.strictSpatialEnabled);
  const setEnabled = useAppStore((s) => s.setStrictSpatialEnabled);
  const result = useAppStore(currentStrictSpatialResult);
  const error = useAppStore((s) => s.strictSpatialError);
  const path = useAppStore((s) => s.evolveproCsvPath);
  const load = useAppStore((s) => s.loadEvolveproCsv);
  const [showPreview, setShowPreview] = useState(false);
  return (
    <div className="mt-2 space-y-2 text-caption" data-testid="strict-spatial-section">
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        {t("strictSpatial.toggle")}
      </label>
      {enabled && <>
        <p className="text-muted-foreground">
          {t("strictSpatial.description")}
        </p>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {!result && <p role="status">{t("strictSpatial.pending")}</p>}
        {path && <button type="button" className="rounded border border-border px-2 py-1 hover:bg-accent"
          onClick={() => { void load(path).catch(() => { /* The store retains the actionable error. */ }); }}>
          {t("strictSpatial.reselect")}
        </button>}
        {result && <>
          <p role="status">{t("strictSpatial.summary", { selected: result.selected_variants.length,
            eligible: result.eligible_site_count, excluded: result.excluded.length })}</p>
          <p>{t("strictSpatial.sourceCoverage", { source: result.source_row_count,
            parsed: result.parsed_variant_count, parsing: result.parsing_omitted_count,
            start: result.start_position_omitted_count, duplicates: result.duplicate_variant_omitted_count })}</p>
          {!result.score_available && <p>{t("strictSpatial.scoresUnavailable")}</p>}
          <p className="break-words font-mono">{result.selected_variants.join(", ")}</p>
          <details>
            <summary>{t("strictSpatial.evidence")}</summary>
            <p className="break-all">{t("strictSpatial.sourceHash", { accession: result.source_accession, hash: result.source_sha256 })}</p>
            <p className="break-all">{t("strictSpatial.referenceHash", { hash: result.reference_sha256 })}</p>
            <p className="break-all">{t("strictSpatial.candidateHash", { hash: result.candidate_sha256 })}</p>
            <p>{t("strictSpatial.policy", { policy: result.selection_policy })}</p>
            {result.excluded.length > 0 && <ul className="max-h-40 overflow-y-auto">
              {result.excluded.map((row, i) => <li key={`${row.variant}-${i}`}>{row.variant}: {row.reason}</li>)}
            </ul>}
          </details>
          <button type="button" className="rounded border border-border px-2 py-1 hover:bg-accent"
            onClick={() => setShowPreview((value) => !value)} aria-expanded={showPreview}>
            {showPreview ? t("strictSpatial.hidePreview") : t("strictSpatial.showPreview")}
          </button>
          {showPreview && <Suspense fallback={<p>{t("strictSpatial.loading")}</p>}><Selection3DPanel defaultOpen embedded /></Suspense>}
        </>}
      </>}
    </div>
  );
}
