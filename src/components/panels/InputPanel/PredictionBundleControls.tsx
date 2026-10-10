import { OptionalDomainAnnotationPanel } from "./OptionalDomainAnnotationPanel";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "@/store/appStore";
import { formatError } from "@/lib/utils";
import { PredictionSourceLinks } from "./PredictionBundleEvidence";

/** Local inspection may default to the producer's top model; chains remain explicit. */
export function PredictionBundleControls() {
  const { t } = useTranslation();
  const source = useAppStore((state) => state.strictStructureSource);
  const setSource = useAppStore((state) => state.setStrictStructureSource);
  const path = useAppStore((state) => state.predictionBundlePath);
  const inventory = useAppStore((state) => state.predictionBundleInventory);
  const modelId = useAppStore((state) => state.predictionBundleModelId);
  const chainId = useAppStore((state) => state.predictionBundleChainId);
  const loading = useAppStore((state) => state.predictionBundleLoading);
  const error = useAppStore((state) => state.predictionBundleError);
  const inspect = useAppStore((state) => state.inspectPredictionBundle);
  const setModel = useAppStore((state) => state.setPredictionBundleModelId);
  const setChain = useAppStore((state) => state.setPredictionBundleChainId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [advancedModels, setAdvancedModels] = useState(false);
  const pickerEpoch = useRef(0);
  useEffect(() => () => { ++pickerEpoch.current; }, [source]);
  useEffect(() => { setAdvancedModels(false); }, [inventory, source]);
  const selectedModel = inventory?.models.find((model) => model.model_id === modelId);
  const showModels = advancedModels || !inventory?.recommended_model_id;
  async function browse() {
    const epoch = ++pickerEpoch.current;
    setDialogOpen(true);
    setDialogError(null);
    try {
      const selected = await open({ title: t("predictionImport.fileDialog"), multiple: false,
        filters: [{ name: "ZIP", extensions: ["zip"] }] });
      if (epoch !== pickerEpoch.current || typeof selected !== "string") return;
      await inspect(selected);
    } catch (cause) {
      if (epoch === pickerEpoch.current) setDialogError(formatError(cause));
    } finally {
      setDialogOpen(false);
    }
  }
  return <section className="min-w-0 space-y-2" aria-label={t("predictionImport.sourceLabel")}>
    <label className="flex min-w-0 flex-wrap items-center gap-2">
      {t("predictionImport.sourceLabel")}
      <select className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1"
        value={source} onChange={(event) => setSource(event.target.value === "prediction_bundle" ? "prediction_bundle" : "accession")}>
        <option value="accession">{t("predictionImport.accessionSource")}</option>
        <option value="prediction_bundle">{t("predictionImport.bundleSource")}</option>
      </select>
    </label>
    {source === "prediction_bundle" && <>
      <p className="text-muted-foreground">{t("predictionImport.localOnly")}</p>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button type="button" disabled={dialogOpen || loading} onClick={() => { void browse(); }}
          className="rounded border border-border px-2 py-1 hover:bg-accent disabled:opacity-50">{t("predictionImport.browse")}</button>
        <span className="min-w-0 flex-1 break-all" title={path}>{path.split(/[\\/]/).pop() || t("predictionImport.noFile")}</span>
      </div>
      {loading && <p role="status">{t("predictionImport.inspecting")}</p>}
      {(error || dialogError) && <div role="alert" className="text-destructive">
        <p>{t("predictionImport.inspectionFailed")}</p><p className="break-words">{error || dialogError}</p>
      </div>}
      {inventory && <>
        <p>{t("predictionImport.format", { format: inventory.format === "af3_server" ? "AF3 Server" : "ColabFold" })}</p>
        <p className="break-all">{t("predictionImport.selectedModel", { model: modelId ?? t("predictionImport.chooseModel") })}</p>
        <p className="text-muted-foreground">{t(inventory.recommended_model_id
          ? "predictionImport.producerDefault" : inventory.recommendation_reason === "missing_top_rank"
            ? "predictionImport.missingTopRank" : "predictionImport.ambiguousRanking")}</p>
        {inventory.recommended_model_id && <button type="button" aria-expanded={showModels}
          onClick={() => setAdvancedModels((previous) => !previous)}
          className="rounded border border-border px-2 py-1 hover:bg-accent">
          {t("predictionImport.advancedModels")}
        </button>}
        {showModels && <label className="flex min-w-0 flex-wrap items-center gap-2">
          {t("predictionImport.modelLabel")}
          <select className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1"
            value={modelId ?? ""} onChange={(event) => setModel(event.target.value || null)}>
            <option value="">{t("predictionImport.chooseModel")}</option>
            {inventory.models.map((model) => <option key={model.model_id} value={model.model_id}>
              {model.producer_rank === null ? model.model_id
                : t("predictionImport.rankedModelOption", { model: model.model_id, rank: model.producer_rank })}
            </option>)}
          </select>
        </label>}
        <label className="flex min-w-0 flex-wrap items-center gap-2">
          {t("predictionImport.chainLabel")}
          <select className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1"
            disabled={!selectedModel} value={chainId === null ? "" : JSON.stringify(chainId)}
            onChange={(event) => setChain(event.target.value === "" ? null : JSON.parse(event.target.value) as string)}>
            <option value="">{t("predictionImport.chooseChain")}</option>
            {selectedModel?.chains.map((chain) => <option key={chain.chain_id} value={JSON.stringify(chain.chain_id)}>
              {t("predictionImport.chainOption", { chain: chain.chain_id || t("predictionImport.blankChain"), length: chain.length })}
            </option>)}
          </select>
        </label>
        <p className="break-all">{t("predictionImport.bundleHash", { hash: inventory.bundle_sha256 })}</p>
        <PredictionSourceLinks source={inventory} />
      </>}
      <OptionalDomainAnnotationPanel />
    </>}
  </section>;
}
