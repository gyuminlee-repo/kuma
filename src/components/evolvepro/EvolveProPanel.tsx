import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useEvolveProStore } from "@/store/evolvepro/evolveProStore";
import { Esm2RecommendationCard } from "./Esm2RecommendationCard";
import { EvolveProOnboardingCard } from "./EvolveProOnboardingCard";
import { EvolveProRunForm } from "./EvolveProRunForm";

/**
 * EvolveProPanel: independent entry point for the EVOLVEpro wrapper module.
 *
 * Not integrated with the main mutation-input flow. Maintains UI continuity by
 * reusing the same shadcn primitives (Card, Button, Input, Progress) and
 * Tailwind tokens (text-foreground, bg-background, border-border) as the rest
 * of KUMA. Locale keys are namespaced under `evolvePro.*` for Wave 1c.
 *
 * Forward-compat: when integration is desired, lift `evolveProResult` from the
 * store and dispatch into `inputSlice.loadEvolveproCsv` at a higher level.
 */
export function EvolveProPanel() {
  const { t } = useTranslation();
  const envStatus = useEvolveProStore((s) => s.evolveProEnvStatus);
  const esm2Recommendation = useEvolveProStore((s) => s.esm2Recommendation);
  const esm2RecommendationLoading = useEvolveProStore((s) => s.esm2RecommendationLoading);
  const detecting = useEvolveProStore((s) => s.evolveProDetecting);
  const detect = useEvolveProStore((s) => s.detectEvolveProEnv);
  const loadEsm2Recommendation = useEvolveProStore((s) => s.loadEsm2Recommendation);

  useEffect(() => {
    if (envStatus === null && !detecting) {
      void detect();
    }
    if (esm2Recommendation === null && !esm2RecommendationLoading) {
      void loadEsm2Recommendation();
    }
  }, [
    envStatus,
    detecting,
    detect,
    esm2Recommendation,
    esm2RecommendationLoading,
    loadEsm2Recommendation,
  ]);

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col gap-4 overflow-y-auto p-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-foreground">
          {t("evolvePro.panel.title", { defaultValue: "EVOLVEpro (Optional)" })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t("evolvePro.panel.description", {
            defaultValue: "Optional variant scoring via user-installed EVOLVEpro. Independent module; main mutation workflow is unaffected.",
          })}
        </p>
      </header>

      <Esm2RecommendationCard
        recommendation={esm2Recommendation}
        loading={esm2RecommendationLoading}
        onRefresh={() => void loadEsm2Recommendation()}
      />

      {envStatus === null || !envStatus.env_found ? (
        <EvolveProOnboardingCard onRetryDetect={() => void detect()} detecting={detecting} />
      ) : (
        <EvolveProRunForm envName="evolvepro" />
      )}
    </div>
  );
}
