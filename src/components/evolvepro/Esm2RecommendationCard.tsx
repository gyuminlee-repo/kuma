import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { AlertTriangle, CheckCircle2, ExternalLink, HardDrive, MemoryStick, Terminal, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { InlineHelp } from "@/components/ui/InlineHelp";
import { Progress } from "@/components/ui/progress";
import { useEvolveProStore } from "@/store/evolvepro/evolveProStore";
import type { Esm2ModelRecommendation, Esm2RecommendationResponse } from "@/types/models.evolvepro";
import { cn } from "@/lib/utils";

interface Esm2RecommendationCardProps {
  recommendation: Esm2RecommendationResponse | null;
  loading: boolean;
  onRefresh: () => void;
}

function formatBytes(n: number): string {
  if (n <= 0) return "0 B";
  if (n >= 1_073_741_824) return `${(n / 1_073_741_824).toFixed(1)} GB`;
  if (n >= 1_048_576) return `${(n / 1_048_576).toFixed(0)} MB`;
  return `${(n / 1024).toFixed(0)} KB`;
}

function statusBadgeVariant(status: Esm2ModelRecommendation["status"]) {
  if (status === "safe") return "success";
  if (status === "caution") return "warning";
  if (status === "blocked") return "destructive";
  return "secondary";
}

function StatusIcon({ status }: { status: Esm2ModelRecommendation["status"] }) {
  if (status === "safe") return <CheckCircle2 className="h-4 w-4 text-verdict-pass" />;
  if (status === "caution") return <AlertTriangle className="h-4 w-4 text-verdict-ambiguous" />;
  if (status === "blocked") return <XCircle className="h-4 w-4 text-verdict-fail" />;
  return <AlertTriangle className="h-4 w-4 text-muted-foreground" />;
}

export function Esm2RecommendationCard({
  recommendation,
  loading,
  onRefresh,
}: Esm2RecommendationCardProps) {
  const { t } = useTranslation();
  const esm2Downloads = useEvolveProStore((s) => s.esm2Downloads);
  const esm2Installed = useEvolveProStore((s) => s.esm2Installed);
  const startEsm2Download = useEvolveProStore((s) => s.startEsm2Download);
  const cancelEsm2Download = useEvolveProStore((s) => s.cancelEsm2Download);
  const refreshEsm2Installed = useEvolveProStore((s) => s.refreshEsm2Installed);
  const activeEsm2ModelId = useEvolveProStore((s) => s.activeEsm2ModelId);
  const setActiveEsm2 = useEvolveProStore((s) => s.setActiveEsm2);
  const resolveActiveEsm2 = useEvolveProStore((s) => s.resolveActiveEsm2);

  // Sync installed state whenever the model list changes
  useEffect(() => {
    if (recommendation?.models && recommendation.models.length > 0) {
      void refreshEsm2Installed();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recommendation?.models]);

  // Auto-resolve active model when recommendation or installed state changes
  useEffect(() => {
    if (recommendation && Object.keys(esm2Installed).length > 0) {
      resolveActiveEsm2();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recommendation, esm2Installed]);
  const installCommand = "python -m pip install fair-esm";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>
              {t("evolvePro.esm2.title", { defaultValue: "ESM2 RAM budget" })}
            </CardTitle>
            <CardDescription>
              {t("evolvePro.esm2.description", {
                defaultValue: "Models above the detected RAM limit are disabled to avoid crashes.",
              })}
            </CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void openShell("https://github.com/facebookresearch/esm")}
              aria-label={t("evolvePro.esm2.docsLink", { defaultValue: "ESM2 docs" })}
            >
              {t("evolvePro.esm2.docsLink", { defaultValue: "ESM2 docs" })}
              <ExternalLink className="ml-1 h-3 w-3" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
              {loading
                ? t("evolvePro.esm2.checking", { defaultValue: "Checking..." })
                : t("evolvePro.esm2.refresh", { defaultValue: "Refresh" })}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {recommendation ? (
          <>
            <div className="grid gap-3 text-sm sm:grid-cols-3">
              <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
                <MemoryStick className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t("evolvePro.esm2.ram", { defaultValue: "RAM" })}
                </span>
                <span className="ml-auto font-medium">
                  {recommendation.ram_gb === null ? "Unknown" : `${recommendation.ram_gb} GB`}
                </span>
              </div>
              <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
                <HardDrive className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {t("evolvePro.esm2.disk", { defaultValue: "Disk" })}
                </span>
                <span className="ml-auto font-medium">
                  {recommendation.disk_free_gb === null ? "Unknown" : `${recommendation.disk_free_gb} GB`}
                </span>
              </div>
              <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                <span className="text-muted-foreground">
                  {t("evolvePro.esm2.system", { defaultValue: "System" })}
                </span>
                <span className="ml-2 font-medium">
                  {recommendation.os} {recommendation.arch}
                </span>
              </div>
            </div>

            {recommendation.recommended_label ? (
              <div className="rounded-md border border-verdict-pass/30 bg-verdict-pass-light/40 px-3 py-2 text-sm">
                <span className="font-medium">
                  {t("evolvePro.esm2.recommended", { defaultValue: "Recommended" })}:{" "}
                  {recommendation.recommended_label}
                </span>
              </div>
            ) : null}

            {/* Active model banner */}
            {(() => {
              const activeLabel = (recommendation.models ?? []).find(
                (m) => m.model_id === activeEsm2ModelId,
              )?.label;
              return activeLabel ? (
                <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
                  <span className="font-medium">
                    {t("evolvePro.esm2.activeModel", {
                      defaultValue: "Active: {{label}}",
                      label: activeLabel,
                    })}
                  </span>
                </div>
              ) : (
                <div className="rounded-md border border-muted px-3 py-2 text-sm text-muted-foreground">
                  {t("evolvePro.esm2.activeModelNone", {
                    defaultValue: "Active: none (select an installed model)",
                  })}
                </div>
              );
            })()}

            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              {t("evolvePro.esm2.download.start", { defaultValue: "Download" })}
              {" / "}
              {t("evolvePro.esm2.download.browser", { defaultValue: "Browser" })}
              <InlineHelp
                text={t("evolvePro.esm2.download.help", {
                  defaultValue:
                    "Download: app handles caching, validation, and atomic write to ~/.cache/torch/hub/checkpoints/. Browser: opens the .pt URL in your default browser (faster with multi-connection managers like aria2 or IDM, but you must manually move the file to the cache folder).",
                })}
                className="ml-1"
              />
            </div>

            <div className="space-y-2">
              {(recommendation.models ?? []).map((model) => {
                const dlState = esm2Downloads[model.model_id];
                const isInstalled = esm2Installed[model.model_id] ?? model.installed;
                const isDownloading = dlState?.status === "downloading";
                const isDone = dlState?.status === "done";
                const hasError = dlState?.status === "error";
                const progressPct =
                  dlState && dlState.total > 0
                    ? Math.round((dlState.bytes / dlState.total) * 100)
                    : 0;

                const isActive = activeEsm2ModelId === model.model_id;
                const canSelect = isInstalled || isDone;

                return (
                  <div
                    key={model.model_id}
                    className={cn(
                      "rounded-md border px-3 py-2 transition-colors",
                      isActive ? "border-primary/60 bg-primary/5" : "border-border",
                    )}
                  >
                    <div className="grid grid-cols-[auto_auto_1fr_auto] items-center gap-3">
                      {/* Radio button */}
                      <input
                        type="radio"
                        name="esm2-active"
                        checked={isActive}
                        disabled={!canSelect}
                        onChange={() => setActiveEsm2(model.model_id)}
                        aria-label={t("evolvePro.esm2.radioAriaLabel", {
                          defaultValue: "Set {{label}} as active model",
                          label: model.label,
                        })}
                        aria-checked={isActive}
                        title={
                          !canSelect
                            ? t("evolvePro.esm2.selectionDisabledHint", {
                                defaultValue: "Download this model first",
                              })
                            : undefined
                        }
                        className="h-4 w-4 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-40"
                      />
                      <StatusIcon status={model.status} />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{model.label}</div>
                        <div className="text-xs text-muted-foreground">
                          {t("evolvePro.esm2.ramRule", {
                            defaultValue: "Minimum {{min}} GB, recommended {{recommended}} GB",
                            min: model.min_ram_gb,
                            recommended: model.recommended_ram_gb,
                          })}
                        </div>
                      </div>
                      <Badge variant={statusBadgeVariant(model.status)}>
                        {t(`evolvePro.esm2.status.${model.status}`, { defaultValue: model.status })}
                      </Badge>
                    </div>

                    {/* Download controls: isDownloading wins over isInstalled so Re-download shows progress */}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {isDownloading ? (
                        <>
                          <div className="flex min-w-[8rem] flex-1 items-center gap-2">
                            <Progress value={progressPct} className="h-2 flex-1" aria-label="Download progress" />
                            <span className="shrink-0 text-xs text-muted-foreground">
                              {formatBytes(dlState.bytes)} / {dlState.total > 0 ? formatBytes(dlState.total) : "?"}
                            </span>
                          </div>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => void cancelEsm2Download(model.model_id)}
                          >
                            {t("evolvePro.esm2.download.cancel", { defaultValue: "Cancel" })}
                          </Button>
                        </>
                      ) : isInstalled || isDone ? (
                        <>
                          <Badge variant="success">
                            {t("evolvePro.esm2.download.installed", { defaultValue: "Installed" })}
                          </Badge>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => void startEsm2Download(model)}
                          >
                            {t("evolvePro.esm2.download.redownload", { defaultValue: "Re-download" })}
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            disabled={model.status === "blocked"}
                            title={
                              model.status === "blocked"
                                ? t("evolvePro.esm2.download.blockedTooltip", { defaultValue: "RAM insufficient" })
                                : undefined
                            }
                            onClick={() => void startEsm2Download(model)}
                          >
                            {t("evolvePro.esm2.download.start", { defaultValue: "Download" })}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => void openShell(model.download_url)}
                          >
                            {t("evolvePro.esm2.download.browser", { defaultValue: "Browser" })}
                            <ExternalLink className="ml-1 h-3 w-3" />
                          </Button>
                        </>
                      )}
                    </div>

                    {/* Inline error message */}
                    {hasError && dlState.error ? (
                      <p className="mt-1 text-xs text-destructive">
                        {t("evolvePro.esm2.download.errorPrefix", { defaultValue: "Download failed: " })}
                        {dlState.error}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>

            {(recommendation.warnings ?? []).length > 0 ? (
              <div className="space-y-1 rounded-md border border-verdict-ambiguous/30 bg-verdict-ambiguous-light/40 px-3 py-2 text-xs">
                {(recommendation.warnings ?? []).map((warning) => (
                  <div key={warning}>{warning}</div>
                ))}
              </div>
            ) : null}

            <div className="space-y-3 rounded-md border border-border bg-muted/30 px-3 py-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Terminal className="h-4 w-4 text-muted-foreground" />
                {t("evolvePro.esm2.installTitle", { defaultValue: "Install ESM support" })}
              </div>
              <p className="text-xs text-muted-foreground">
                {t("evolvePro.esm2.installDescription", {
                  defaultValue:
                    "Install fair-esm in the Python environment used by EVOLVEpro before generating new ESM2 embeddings.",
                })}
              </p>
              <code className="block overflow-x-auto rounded-md border border-border bg-background px-3 py-2 text-xs">
                {installCommand}
              </code>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void openShell("https://pypi.org/project/fair-esm/")}
                >
                  PyPI
                  <ExternalLink className="ml-1 h-3 w-3" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void openShell("https://github.com/facebookresearch/esm")}
                >
                  GitHub
                  <ExternalLink className="ml-1 h-3 w-3" />
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-3 text-sm text-muted-foreground">
            {loading
              ? t("evolvePro.esm2.loading", { defaultValue: "Checking system RAM..." })
              : t("evolvePro.esm2.empty", { defaultValue: "Run a system check to see available ESM2 models." })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
