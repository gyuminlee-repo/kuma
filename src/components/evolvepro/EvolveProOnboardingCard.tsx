import { useTranslation } from "react-i18next";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CondaSetupWizard } from "@/components/evolvepro/CondaSetupWizard";
import { useCondaSetupStore } from "@/store/evolvepro/condaSetupStore";

export interface EvolveProOnboardingCardProps {
  onRetryDetect: () => void;
  detecting: boolean;
}

/**
 * Inline onboarding card shown when EVOLVEpro conda env is not detected.
 * Not a modal Dialog. Does not block the main flow. Contains user-actionable
 * setup instructions and an EULA disclaimer.
 * The setup wizard button opens a guided modal for automated installation.
 */
export function EvolveProOnboardingCard({ onRetryDetect, detecting }: EvolveProOnboardingCardProps) {
  const { t } = useTranslation();
  const { setOpen, detect } = useCondaSetupStore();
  const setupCommand =
    "conda create -n evolvepro -c conda-forge python=3.11 pip -y\n" +
    "conda activate evolvepro\n" +
    "pip install \"numpy<2.0\" pandas openpyxl scikit-learn scikit-learn-extra xgboost matplotlib seaborn biopython scipy torch fair-esm https://github.com/mat10d/EvolvePro/archive/refs/heads/main.zip";

  function handleOpenWizard() {
    setOpen(true);
    void detect();
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>{t("evolvePro.onboarding.title", { defaultValue: "EVOLVEpro environment not found" })}</CardTitle>
          <CardDescription>
            {t("evolvePro.onboarding.description", {
              defaultValue: "KUMA does not bundle EVOLVEpro. Install it in a conda environment named `evolvepro` to enable variant scoring.",
            })}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleOpenWizard} size="sm">
              {t("conda.wizard.openButton", { defaultValue: "Run setup wizard" })}
            </Button>
            <Button onClick={onRetryDetect} disabled={detecting} size="sm" variant="outline">
              {detecting
                ? t("evolvePro.onboarding.detecting", { defaultValue: "Detecting..." })
                : t("evolvePro.onboarding.retry", { defaultValue: "Re-check environment" })}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.onboarding.singleEnvNote", {
              defaultValue: "The official EVOLVEpro docs use a separate PLM environment. This GUI combines EVOLVEpro, ESM, and PyTorch in one environment for desktop runs.",
            })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.onboarding.manualFallback", {
              defaultValue: "If the wizard fails, install the GUI's single-env setup manually:",
            })}
          </p>
          <pre className="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 text-xs">
            <code>{setupCommand}</code>
          </pre>
          <p className="text-xs text-muted-foreground">
            {t("evolvePro.onboarding.eula", {
              defaultValue: "EVOLVEpro is licensed under MIT TLO Internal Research EULA. Installation implies acceptance of those terms; KUMA only shells out to the user-installed binary.",
            })}
          </p>
        </CardContent>
      </Card>
      <CondaSetupWizard />
    </>
  );
}
