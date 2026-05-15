import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
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
  const envStatus = useAppStore((s) => s.evolveProEnvStatus);
  const detecting = useAppStore((s) => s.evolveProDetecting);
  const detect = useAppStore((s) => s.detectEvolveProEnv);

  useEffect(() => {
    if (envStatus === null && !detecting) {
      void detect();
    }
  }, [envStatus, detecting, detect]);

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

      {envStatus === null || !envStatus.env_found ? (
        <EvolveProOnboardingCard onRetryDetect={() => void detect()} detecting={detecting} />
      ) : (
        <EvolveProRunForm envName="evolvepro" />
      )}
    </div>
  );
}
