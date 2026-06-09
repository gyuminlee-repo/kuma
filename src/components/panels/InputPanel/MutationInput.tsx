import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { browseFile } from "../../../lib/file-utils";
import { useArtifact } from "../../../lib/workspace";
import { Button } from "../../ui/button";
import { InlineHelp } from "../../ui/InlineHelp";
import { ArtifactBadge } from "../../widgets/ArtifactBadge";
import { OthersPanel } from "./OthersPanel";
import { EvolveproSelectTable } from "../../widgets/EvolveproSelectTable";

export function MutationInput() {
  const { t } = useTranslation();
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const mutationText = useAppStore((s) => s.mutationText);
  const parsedMutations = useAppStore((s) => s.parsedMutations);
  const parseErrors = useAppStore((s) => s.parseErrors);
  const setMutationInputMode = useAppStore((s) => s.setMutationInputMode);
  const evolveproCsvPath = useAppStore((s) => s.evolveproCsvPath);
  const othersSourcePath = useAppStore((s) => s.othersSourcePath);
  const loadEvolveproCsv = useAppStore((s) => s.loadEvolveproCsv);
  const setOthersSourcePath = useAppStore((s) => s.setOthersSourcePath);
  const setOthersPreview = useAppStore((s) => s.setOthersPreview);
  const setOthersVariantColumn = useAppStore((s) => s.setOthersVariantColumn);
  const setOthersScoreColumn = useAppStore((s) => s.setOthersScoreColumn);
  const artifact = useArtifact("evolvepro_csv");
  const [userOverridden, setUserOverridden] = useState(false);

  // Auto-prefill from workspace manifest when user hasn't manually overridden.
  useEffect(() => {
    if (userOverridden) return;
    if (!artifact) return;
    if (artifact.path === evolveproCsvPath) return;
    void loadEvolveproCsv(artifact.path);
  }, [artifact, userOverridden, evolveproCsvPath, loadEvolveproCsv]);

  const showArtifactBadge =
    artifact !== null && !userOverridden && artifact.path === evolveproCsvPath;
  const evolveproMode = useAppStore((s) => s.evolveproMode);
  const setEvolveproMode = useAppStore((s) => s.setEvolveproMode);
  const evolveproTotalCount = useAppStore((s) => s.evolveproTotalCount);
  const evolveproRankedCandidates = useAppStore((s) => s.evolveproRankedCandidates);
  const evolveproSelectedVariants = useAppStore((s) => s.evolveproSelectedVariants);
  const evolveproExtraExposed = useAppStore((s) => s.evolveproExtraExposed);
  const setEvolveproVariantSelected = useAppStore((s) => s.setEvolveproVariantSelected);
  const activeTablePath = evolveproMode === "others" ? othersSourcePath : evolveproCsvPath;

  const mutationCount = useMemo(
    () =>
      mutationText
        .split("\n")
        .filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  const { pickerRows, bufferCap } = useMemo(() => {
    const selectedSet = new Set(evolveproSelectedVariants);
    const unselectedBuffer = evolveproRankedCandidates
      .filter((c) => !selectedSet.has(c.variant))
      .slice(0, evolveproExtraExposed);
    const rows = [
      ...evolveproRankedCandidates
        .filter((c) => selectedSet.has(c.variant))
        .map((c) => ({
          variant: c.variant,
          yPred: c.y_pred,
          aaPosition: c.aa_position ?? null,
          selected: true,
        })),
      ...unselectedBuffer.map((c) => ({
        variant: c.variant,
        yPred: c.y_pred,
        aaPosition: c.aa_position ?? null,
        selected: false,
      })),
    ];
    const cap =
      evolveproRankedCandidates.length -
      evolveproSelectedVariants.filter((v) =>
        evolveproRankedCandidates.some((c) => c.variant === v),
      ).length;
    return { pickerRows: rows, bufferCap: cap };
  }, [evolveproSelectedVariants, evolveproRankedCandidates, evolveproExtraExposed]);

  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-foreground inline-flex items-center gap-1.5">
        {t("mutationInput.mutations")}
        <InlineHelp text={t("mutationInput.mutationsHelp")} />
      </label>
      <div className="flex flex-wrap gap-2 text-xs" role="radiogroup" aria-label={t("mutationInput.mutationInputAriaLabel")}>
        <label className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-muted-foreground">
          <input
            type="radio"
            name="mutInput"
            checked={mutationInputMode === "evolvepro" && evolveproMode !== "others"}
            onChange={() => {
              setMutationInputMode("evolvepro");
              setEvolveproMode("topN");
            }}
            className="w-3 h-3"
          />
          EVOLVEpro
        </label>
        <label className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-muted-foreground">
          <input
            type="radio"
            name="mutInput"
            checked={mutationInputMode === "evolvepro" && evolveproMode === "others"}
            onChange={() => {
              setMutationInputMode("evolvepro");
              setEvolveproMode("others");
            }}
            className="w-3 h-3"
          />
          {t("mutationInput.others")}
        </label>
      </div>

      {mutationInputMode === "evolvepro" && (
        <div className="space-y-2">
          {/* CSV / XLSX file loader (shared by evolvepro and others modes) */}
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                browseFile(
                  [
                    {
                      name: "EVOLVEpro CSV/TSV/XLSX",
                      extensions: ["csv", "tsv", "xlsx", "xls"],
                    },
                  ],
                  (path) => {
                    setUserOverridden(true);
                    if (evolveproMode === "others") {
                      setOthersSourcePath(path);
                      setOthersPreview(null);
                      setOthersVariantColumn(null);
                      setOthersScoreColumn(null);
                      return;
                    }
                    loadEvolveproCsv(path);
                  },
                )
              }
              className="flex-shrink-0"
            >
              Browse
            </Button>
            <span className="self-center truncate text-xs text-muted-foreground">
              {activeTablePath ? basename(activeTablePath) : t("mutationInput.noFileSelected")}
            </span>
            {showArtifactBadge && artifact && (
              <ArtifactBadge artifact={artifact} className="self-center" />
            )}
          </div>

          {/* Variant count summary */}
          {evolveproTotalCount > 0 && (
            <div className="rounded-xl border border-border bg-muted px-3 py-2 text-xs font-medium text-foreground">
              EVOLVEpro:{" "}
              {t("mutationInput.variantsLoaded", { count: evolveproTotalCount })}
            </div>
          )}

          {/* Others mode: column mapping panel */}
          {evolveproMode === "others" && <OthersPanel />}

          {/* topN / pipeline mode: selection mode radiogroup */}
          {evolveproMode !== "others" && (
            <div className="space-y-1">
              <div className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">
                {t("mutationInput.selectionMode")}
              </div>
              <div className="space-y-0.5">
                <label className="flex items-center gap-1.5 cursor-pointer text-xs">
                  <input
                    type="radio"
                    name="selectionMode"
                    className="w-3 h-3"
                    checked={evolveproMode === "topN"}
                    onChange={() => setEvolveproMode("topN")}
                  />
                  <span className="text-foreground">{t("mutationInput.topNOnly")}</span>
                  <span className="text-caption text-muted-foreground">{t("mutationInput.topNDesc")}</span>
                </label>
                <div className="ml-5 text-caption text-muted-foreground/70">
                  {t("mutationInput.topNZeroHint")}
                </div>
                <label className="flex items-center gap-1.5 cursor-pointer text-xs">
                  <input
                    type="radio"
                    name="selectionMode"
                    className="w-3 h-3"
                    checked={evolveproMode === "pipeline"}
                    onChange={() => setEvolveproMode("pipeline")}
                  />
                  <span className="text-foreground">{t("mutationInput.pipeline")}</span>
                  <span className="text-caption text-muted-foreground">{t("mutationInput.pipelineDesc")}</span>
                </label>
              </div>
            </div>
          )}

          {/* EVOLVEpro candidate picker (topN / pipeline only) */}
          {evolveproMode !== "others" && evolveproRankedCandidates.length > 0 && (() => {
            return (
              <div className="space-y-1">
                <EvolveproSelectTable
                  rows={pickerRows}
                  onToggle={(variant, checked) => setEvolveproVariantSelected(variant, checked)}
                />
                {evolveproExtraExposed >= bufferCap && bufferCap > 0 && (
                  <p className="text-caption text-muted-foreground">
                    {t("mutationInput.bufferCapReached", { count: bufferCap })}
                  </p>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {mutationText.trim() && (
        <div className="text-xs text-muted-foreground">
          {t("mutationInput.mutationsEntered", { count: mutationCount })}
          {parsedMutations.length > 0 && (
            <span className="ml-1 text-emerald-600">
              {t("mutationInput.mutationsValidated", { count: parsedMutations.length })}
            </span>
          )}
          {parseErrors.length > 0 && (
            <span className="text-destructive ml-1">{t("mutationInput.mutationsFailed", { count: parseErrors.length })}</span>
          )}
        </div>
      )}
      {parseErrors.length > 0 && (
        <div className="max-h-16 space-y-0.5 overflow-auto rounded-md bg-destructive/10 px-2 py-1 text-caption text-destructive">
          {parseErrors.map((e) => (
            <div key={e.line}>
              L{e.line}: <span className="font-mono">{e.raw}</span> — {e.reason}
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
