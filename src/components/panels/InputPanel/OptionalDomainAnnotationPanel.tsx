import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "@/store/appStore";
import { currentDomainAnnotation, domainAnnotationContextKey, domainAnnotationSource, domainJobIsActive,
  domainReferenceSequence, domainSelectionDistribution, formatDomainPositions } from "@/lib/domainAnnotation";
import { formatError } from "@/lib/utils";
import type { DomainAnnotationResult } from "@/types/domainAnnotation";

const buttonStyle = "rounded border border-border px-2 py-1 hover:bg-accent disabled:opacity-50";

function DomainAnnotationSummary({ result }: { result: DomainAnnotationResult }) {
  const { t } = useTranslation();
  const reference = useAppStore(domainReferenceSequence);
  const variants = useAppStore((state) => state.evolveproSelectedVariants);
  const distribution = domainSelectionDistribution(result, reference, variants);
  const percent = (value: number) => `${Number((100 * value).toFixed(1))}%`;
  return <section className="min-w-0 space-y-2" aria-label={t("optionalDomains.results")}>
    <p>{t("optionalDomains.coverage", { assigned: result.assigned_residues, total: result.total_residues, coverage: percent(result.coverage) })}</p>
    <p>{t("optionalDomains.confidence", { confidence: percent(result.confidence) })}</p>
    <p className="text-muted-foreground">{t("optionalDomains.confidenceMeaning")}</p>
    <p>{t(result.provenance === "managed" ? "optionalDomains.managedProvenance" : "optionalDomains.importedProvenance")}</p>
    <table className="w-full table-fixed text-caption">
      <caption className="text-left font-medium">{t("optionalDomains.distribution")}</caption>
      <thead><tr>
        <th className="break-words text-left" scope="col">{t("optionalDomains.partition")}</th>
        <th className="break-words text-right" scope="col">{t("optionalDomains.variants")}</th>
        <th className="break-words text-right" scope="col">{t("optionalDomains.sites")}</th>
      </tr></thead>
      <tbody>{[...result.domains.map((d) => d.positions), result.unassigned_positions].map((positions, index) => <tr key={index}>
        <th scope="row" className="break-words text-left font-normal">
          <span>{index === result.domains.length ? t("optionalDomains.unassigned") : t("optionalDomains.domain", { index: index + 1 })}</span>
          <div className="font-mono">{formatDomainPositions(positions) || "0"}</div>
        </th>
        <td className="text-right tabular-nums">{distribution ? `${distribution[index].variantCount}${distribution[index].fraction === null ? "" : ` (${percent(distribution[index].fraction)})`}` : "—"}</td>
        <td className="text-right tabular-nums">{distribution ? distribution[index].siteCount : "—"}</td>
      </tr>)}</tbody>
    </table>
    <p className="text-muted-foreground">{t("optionalDomains.distributionMeaning")}</p>
    {!distribution && <p role="status">{t("optionalDomains.distributionUnavailable")}</p>}
    <details className="min-w-0">
      <summary>{t("optionalDomains.provenance")}</summary>
      <p>{t("optionalDomains.engine", { engine: result.engine })}</p>
      <p className="break-all">{t("predictionImport.selected", { model: result.binding.model_id, chain: result.binding.chain_id || t("predictionImport.blankChain") })}</p>
      <p className="break-all">{t("predictionImport.bundleHash", { hash: result.binding.bundle_sha256 })}</p>
      <p className="break-all">{t("predictionImport.structureHash", { hash: result.binding.source_sha256 })}</p>
      <p className="break-all">{t("strictSpatial.referenceHash", { hash: result.binding.reference_sha256 })}</p>
      <p className="break-all">{t("optionalDomains.bindingHash", { hash: result.binding_sha256 })}</p>
      <p className="break-words">{result.provenance_note}</p>
    </details>
  </section>;
}

/** Explicit opt-in explanation and controls, separate from the spatial selector. */
export function OptionalDomainAnnotationPanel() {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [pickerBusy, setPickerBusy] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const pickerEpoch = useRef(0);
  const context = useAppStore(domainAnnotationContextKey);
  const ready = useAppStore((state) => domainAnnotationSource(state) !== null);
  const format = useAppStore((state) => state.predictionBundleInventory?.format);
  const runtime = useAppStore((state) => state.domainRuntimeStatus);
  const runtimeLoading = useAppStore((state) => state.domainRuntimeLoading);
  const job = useAppStore((state) => state.domainAnnotationJob);
  const attempt = useAppStore((state) => state.domainAnnotationAttempt);
  const pending = useAppStore((state) => state.domainAnnotationPending);
  const error = useAppStore((state) => state.domainAnnotationError);
  const result = useAppStore(currentDomainAnnotation);
  const refresh = useAppStore((state) => state.refreshDomainRuntime);
  const install = useAppStore((state) => state.installDomainRuntime);
  const remove = useAppStore((state) => state.removeDomainRuntime);
  const start = useAppStore((state) => state.startDomainAnnotation);
  const cancel = useAppStore((state) => state.cancelDomainAnnotation);
  const reset = useAppStore((state) => state.resetDomainAnnotation);
  const importFile = useAppStore((state) => state.importDomainAnnotationFile);
  const active = domainJobIsActive(job?.state);
  const busy = Boolean(active || pending || runtimeLoading || pickerBusy);
  useEffect(() => {
    const unsubscribe = useAppStore.subscribe((next, previous) => {
      if (domainAnnotationContextKey(next) !== domainAnnotationContextKey(previous)) {
        ++pickerEpoch.current; setPickerBusy(false); setPickerError(null);
      }
    });
    return () => { unsubscribe(); ++pickerEpoch.current; };
  }, []);
  useEffect(() => { setPickerError(null); setPickerBusy(false); }, [context]);
  useEffect(() => { if (expanded && !runtime) void refresh(); }, [expanded, refresh, runtime]);

  async function browse(kind: "install" | "import") {
    const epoch = ++pickerEpoch.current;
    setPickerBusy(true); setPickerError(null);
    try {
      const selected = await open({ title: t(kind === "install" ? "optionalDomains.install" : "optionalDomains.import"), multiple: false,
        filters: [{ name: kind === "install" ? "ZIP" : "JSON", extensions: [kind === "install" ? "zip" : "json"] }] });
      if (epoch !== pickerEpoch.current || context !== domainAnnotationContextKey(useAppStore.getState()) || typeof selected !== "string") return;
      if (kind === "install") await install(selected); else await importFile(selected);
    } catch (cause) {
      if (epoch === pickerEpoch.current) setPickerError(formatError(cause));
    } finally { if (epoch === pickerEpoch.current) setPickerBusy(false); }
  }
  return <section className="min-w-0 space-y-2 rounded border border-border p-2" aria-label={t("optionalDomains.title")}>
    <button type="button" className={buttonStyle} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {t("optionalDomains.title")}
    </button>
    {expanded && <>
      <p>{t("optionalDomains.annotationOnly")}</p>
      <p className="text-muted-foreground">{t("optionalDomains.originalAtoms")}</p>
      {!ready && <p>{t(format === "af3_server" ? "optionalDomains.unsupportedAf3" : "optionalDomains.inputRequired")}</p>}
      <p className="text-muted-foreground">{t("optionalDomains.inputLimits")}</p>
      {runtimeLoading && <p role="status">{t("optionalDomains.runtimeChecking")}</p>}
      {runtime && <>
        <p role="status">{t(`optionalDomains.runtime.${runtime.state}`)}</p>
        <p>{t("optionalDomains.runtimeIdentity", { engine: runtime.engine, platform: runtime.platform, version: runtime.version ?? t("predictionImport.unknown") })}</p>
        {!runtime.install_available && runtime.state !== "installed" && <p>{t("optionalDomains.packageUnavailable")}</p>}
        <details><summary>{t("optionalDomains.details")}</summary><p className="break-words">{runtime.message}</p></details>
      </>}
      <div className="flex min-w-0 flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => { void refresh(); }} className={buttonStyle}>{t("optionalDomains.refresh")}</button>
        <button type="button" disabled={busy || !runtime?.install_available} title={!runtime?.install_available ? t("optionalDomains.packageUnavailable") : undefined}
          onClick={() => { void browse("install"); }} className={buttonStyle}>{t("optionalDomains.install")}</button>
        <button type="button" disabled={busy || !runtime || !["installed", "corrupt"].includes(runtime.state)}
          onClick={() => { void remove(); }} className={buttonStyle}>{t("optionalDomains.remove")}</button>
      </div>
      <div className="flex min-w-0 flex-wrap gap-2">
        <button type="button" disabled={busy || !ready || runtime?.state !== "installed"}
          title={!ready ? t("optionalDomains.inputRequired") : runtime?.state !== "installed" ? t("optionalDomains.packageUnavailable") : undefined}
          onClick={() => { void start(); }} className={buttonStyle}>{t("optionalDomains.run")}</button>
        <button type="button" disabled={busy || !ready} onClick={() => { void browse("import"); }} className={buttonStyle}>{t("optionalDomains.import")}</button>
        {(active || pending === "starting" || pending === "cancelling") && <button type="button"
          disabled={pending === "cancelling" || job?.state === "cancelling"} onClick={() => { void cancel(); }} className={buttonStyle}>{t("common.cancel")}</button>}
        <button type="button" onClick={() => { ++pickerEpoch.current; setPickerBusy(false); setPickerError(null); reset(); }} className={buttonStyle}>{t("optionalDomains.reset")}</button>
      </div>
      {(pending || job || attempt) && <div role="status" aria-live="polite">
        <p>{pending ? t(`optionalDomains.job.${pending}`) : job ? t(`optionalDomains.job.${job.state}`) : attempt?.state === "cancelled" ? t("optionalDomains.job.cancelled") : null}</p>
        {(active || pending) && <progress className="w-full" aria-label={t("optionalDomains.progress")} />}
        {(job || attempt?.message) && <details><summary>{t("optionalDomains.details")}</summary><p className="break-words">{job?.message ?? attempt?.message}</p></details>}
      </div>}
      {(error || pickerError) && <div role="alert" className="text-destructive">
        <p>{t("optionalDomains.failedHint")}</p><details><summary>{t("optionalDomains.details")}</summary><p className="break-words">{error || pickerError}</p></details>
      </div>}
      {result && <DomainAnnotationSummary result={result} />}
    </>}
  </section>;
}
