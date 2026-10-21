import { useTranslation } from "react-i18next";
import { useState } from "react";
import { MameRunStoreContext, resequenceStore, useMameAppStore } from "@/store/mame/mameAppStore";
import { AnalyzeStepView } from "./AnalyzeStepView";
import { AdditionalSequencingPanel } from "@/components/mame/widgets/AdditionalSequencingPanel";
import { Button } from "@/components/ui/button";
import { ClearConfirmDialog } from "@/components/dialogs/ClearConfirmDialog";
import { WizardContainer } from "@/components/steps/WizardContainer";

function IndependentAnalysis({ onNext, onPrev, onRunRequest }: { onNext: () => void; onPrev: () => void; onRunRequest?: () => void }) {
  const { t } = useTranslation();
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setSubStep = useMameAppStore((s) => s.setMameSubStep);
  const runHealth = useMameAppStore((s) => s.runHealth);
  const clear = useMameAppStore((s) => s.clearResults);
  const [clearOpen, setClearOpen] = useState(false);
  return (
    <div className="flex h-full min-h-0 flex-col text-foreground">
      <div className="flex flex-wrap gap-2 px-4 py-2">
        <Button variant={subStep === "analyze.inputs" ? "secondary" : "ghost"} onClick={() => setSubStep("analyze.inputs")}>
          {t("phaseC.mameSubSteps.analyze.inputs")}
        </Button>
        <Button variant={subStep === "analyze.review" ? "secondary" : "ghost"} onClick={() => setSubStep("analyze.review")}>
          {t("phaseC.mameSubSteps.analyze.review")}
        </Button>
      </div>
      <div className="min-h-0 flex-1">
        <AnalyzeStepView independent runHealth={runHealth} onRunRequest={onRunRequest} onClearRequest={() => setClearOpen(true)} onNextRequest={onNext} onPrevRequest={onPrev} />
      </div>
      <ClearConfirmDialog open={clearOpen} onOpenChange={setClearOpen} onConfirm={clear} />
    </div>
  );
}

export function ResequenceStepView({ onRunRequest }: { onRunRequest?: () => void }) {
  const setSubStep = useMameAppStore((s) => s.setMameSubStep);
  return (
    <MameRunStoreContext.Provider value={resequenceStore}>
      <IndependentAnalysis onRunRequest={onRunRequest} onNext={() => setSubStep("analyze.confirm")} onPrev={() => setSubStep("analyze.review")} />
    </MameRunStoreContext.Provider>
  );
}

/** Manual confirmation is auxiliary, never the resequencing analysis itself. */
export function ManualConfirmationStepView() {
  const { t } = useTranslation();
  const next = useMameAppStore((s) => s.goToNextStep);
  const prev = useMameAppStore((s) => s.goToPrevStep);
  return (
    <WizardContainer stepIndex={4} stepTotal={4} stepLabel="2.4" progressLabel="2.4 / 4"
      titleKey="mame.resequence.manualTitle" descriptionKey="mame.resequence.manualDescription"
      onNext={next} onPrev={prev}>
    <div className="space-y-6 text-foreground">
      <section aria-label={t("mame.resequence.primary")}>
        <h2 className="mb-2 text-title font-semibold">{t("mame.resequence.primary")}</h2>
        <AdditionalSequencingPanel />
      </section>
      <MameRunStoreContext.Provider value={resequenceStore}>
        <section aria-label={t("mame.resequence.title")}>
          <h2 className="mb-2 text-title font-semibold">{t("mame.resequence.title")}</h2>
          <AdditionalSequencingPanel />
        </section>
      </MameRunStoreContext.Provider>
    </div>
    </WizardContainer>
  );
}
