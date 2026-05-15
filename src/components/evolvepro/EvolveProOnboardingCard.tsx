import { useTranslation } from "react-i18next";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export interface EvolveProOnboardingCardProps {
  onRetryDetect: () => void;
  detecting: boolean;
}

/**
 * Inline onboarding card shown when EVOLVEpro conda env is not detected.
 * Not a modal Dialog. Does not block the main flow. Contains user-actionable
 * setup instructions and an EULA disclaimer.
 */
export function EvolveProOnboardingCard({ onRetryDetect, detecting }: EvolveProOnboardingCardProps) {
  const { t } = useTranslation();
  const setupCommand = "conda create -n evolvepro -c conda-forge python=3.11 -y\nconda activate evolvepro\npip install evolvepro";
  return (
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
        <pre className="overflow-x-auto rounded-md border border-border bg-muted px-3 py-2 text-xs">
          <code>{setupCommand}</code>
        </pre>
        <p className="text-xs text-muted-foreground">
          {t("evolvePro.onboarding.eula", {
            defaultValue: "EVOLVEpro is licensed under MIT TLO Internal Research EULA. Installation implies acceptance of those terms; KUMA only shells out to the user-installed binary.",
          })}
        </p>
        <Button onClick={onRetryDetect} disabled={detecting} size="sm">
          {detecting
            ? t("evolvePro.onboarding.detecting", { defaultValue: "Detecting…" })
            : t("evolvePro.onboarding.retry", { defaultValue: "Re-check environment" })}
        </Button>
      </CardContent>
    </Card>
  );
}
