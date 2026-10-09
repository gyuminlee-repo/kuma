import { useState } from "react";
import { useTranslation } from "react-i18next";
import { openUrl } from "@tauri-apps/plugin-opener";
import type { PredictionBundleEvidence as Evidence, PredictionBundleInventory } from "@/types/models";

export function PredictionSourceLinks({ source }: { source: Pick<PredictionBundleInventory, "format" | "source_url" | "terms_url"> }) {
  const { t } = useTranslation();
  const [error, setError] = useState(false);
  const link = (href: string, label: string) => <a className="underline" href={href} onClick={(event) => {
    event.preventDefault();
    setError(false);
    void openUrl(href).catch(() => setError(true));
  }}>{label}</a>;
  return <div className="space-y-1">
    <p>{link(source.source_url, t("predictionImport.sourceLink"))}</p>
    {source.format === "af3_server" && <>
      <p>{t("predictionImport.termsNotice")}</p>
      {source.terms_url && <p>{link(source.terms_url, t("predictionImport.terms"))}</p>}
    </>}
    {error && <p role="alert" className="text-destructive">{t("predictionImport.openLinkFailed")}</p>}
  </div>;
}

export function PredictionBundleEvidence({ evidence }: { evidence: Evidence }) {
  const { t } = useTranslation();
  const known = evidence.plddt_by_reference.filter((value): value is number => value !== null);
  const format = (value: number | null) => value === null ? t("predictionImport.unknown") : String(Number(value.toPrecision(4)));
  return <section className="min-w-0 space-y-1" aria-label={t("predictionImport.bundleSource")}>
    <p className="break-all">{t("predictionImport.source", { name: evidence.source_name })}</p>
    <p>{t("predictionImport.format", { format: evidence.format === "af3_server" ? "AF3 Server" : "ColabFold" })}</p>
    <p className="break-all">{t("predictionImport.selected", { model: evidence.model_id, chain: evidence.chain_id || t("predictionImport.blankChain") })}</p>
    <p>{t("predictionImport.confidence", { known: known.length, total: evidence.plddt_by_reference.length,
      pae: t(evidence.pae.status === "available" ? "predictionImport.available" : "predictionImport.unknown") })}</p>
    <p>{t("predictionImport.plddtSummary", { min: format(known.length ? Math.min(...known) : null),
      mean: format(known.length ? known.reduce((sum, value) => sum + value, 0) / known.length : null) })}</p>
    {evidence.pae.status === "available" && <p>{t("predictionImport.paeSummary", { mean: format(evidence.pae.mean), max: format(evidence.pae.max) })}</p>}
    <p>{t("predictionImport.paeMeaning")}</p>
    <p>{t("predictionImport.confidenceMeaning")}</p>
    <p>{t("predictionImport.caOnly")}</p>
    <details>
      <summary>{t("strictSpatial.evidence")}</summary>
      <p className="break-all">{t("predictionImport.bundleHash", { hash: evidence.bundle_sha256 })}</p>
      <p className="break-all">{evidence.structure_member}</p>
      <p className="break-all">{t("predictionImport.structureHash", { hash: evidence.structure_sha256 })}</p>
      <p className="break-all">{evidence.confidence_member ?? t("predictionImport.unknown")}</p>
      <p className="break-all">{t("predictionImport.confidenceHash", { hash: evidence.confidence_sha256 ?? t("predictionImport.unknown") })}</p>
      <p className="break-all">{t("predictionImport.displayHash", { hash: evidence.display_sha256 })}</p>
      {evidence.sequence_sha256 && <>
        <p className="break-all">{evidence.sequence_member}</p>
        <p className="break-all">{t("predictionImport.sequenceHash", { hash: evidence.sequence_sha256 })}</p>
      </>}
      <p className="break-words">{evidence.plddt_source}</p>
      {evidence.source_notices && evidence.source_notices.length > 0 && <details>
        <summary>{t("predictionImport.bundledNotices")}</summary>
        {evidence.source_notices.map((notice) => <div key={notice.member}>
          <p className="break-all">{notice.member} · {notice.sha256}</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words">{notice.text}</pre>
        </div>)}
      </details>}
      {evidence.warnings.length > 0 && <ul>{evidence.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      <PredictionSourceLinks source={evidence} />
    </details>
  </section>;
}
