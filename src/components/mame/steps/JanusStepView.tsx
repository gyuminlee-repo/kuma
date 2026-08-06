/**
 * JanusStepView, "janus" mame phase, step 3.1 (Janus instrument settings).
 *
 * The instrument configuration used to sit inside step 2.1 (inputs), which made
 * an operator who only wants a sequencing verdict walk past a cell-picking robot
 * they are not going to use. It is its own major step now: step 2 ends at the
 * verdict, step 3 is the instrument, step 4 is the activity data.
 *
 * The step stays optional in the strict sense: nothing here gates a run and
 * nothing downstream gates on it. An analyze run writes `..._picks.csv` on its
 * own from whatever is stored (the selection, `legacy5`); the instrument
 * mapping (`..._janus.csv`, `device9`) is written only from here, by the export
 * button in `JanusMappingPanel` below, because a robot worklist states a deck
 * and a liquid class that describe the room at export time, and analyze has no
 * reason to assert either on every re-run.
 *
 * What lives here:
 *   - what the last run did with the pick list it writes automatically
 *   - the mapping panel (transfer volume, liquid class, deck rack numbers, row
 *     preview, excluded clones, and the mapping export itself). Used to be a
 *     dialog opened from a button here; step 3 is already a dedicated screen,
 *     so it is inlined now.
 *
 * The step asks for nothing of its own. It used to carry a transfer volume
 * input above the panel, but that input and the panel's Volume field wrote the
 * same stored `janusSettings.volume`, so the operator was answering one
 * question twice. The panel's field renders unconditionally, so removing the
 * one up here loses no way to set the value.
 */

import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { JanusMappingPanel } from "@/components/mame/widgets/JanusMappingPanel";
import { JanusAutosaveNotice } from "@/components/mame/widgets/JanusAutosaveNotice";
import { StepRedirectFallback } from "./StepRedirectFallback";

const JANUS_TOTAL = 1;

export function JanusStepView() {
  const { t } = useTranslation();
  const subStep = useMameAppStore((s) => s.currentMameSubStep);
  const setMameSubStep = useMameAppStore((s) => s.setMameSubStep);
  const goToPrevStep = useMameAppStore((s) => s.goToPrevStep);
  const goToNextStep = useMameAppStore((s) => s.goToNextStep);

  if (subStep !== "janus.settings") {
    return (
      <StepRedirectFallback
        currentSub={subStep}
        expectedFor="janus"
        setSubStep={setMameSubStep}
      />
    );
  }

  return (
    <WizardContainer
      stepIndex={1}
      stepTotal={JANUS_TOTAL}
      stepLabel="3.1"
      progressLabel={`3.1 / ${JANUS_TOTAL}`}
      titleKey="phaseC.mameSubSteps.janus.settings"
      descriptionKey="phaseE.mameDescriptions.janus.settings"
      onPrev={goToPrevStep}
      onNext={goToNextStep}
    >
      <div className="space-y-4">
        {/* Said before anything is asked for: the step can be left alone. */}
        <p
          className="rounded-control border border-border bg-muted/30 px-3 py-2 text-caption text-muted-foreground"
          data-testid="janus-optional-note"
        >
          {t("mame.janus.settings.optionalNote")}
        </p>

        {/* What the last run did with the pick list it writes itself. The
            instrument mapping has no autosave notice: it is only ever
            written by the export button below, so there is nothing
            automatic to report on. */}
        <JanusAutosaveNotice />

        {/* Was a button that opened a modal carrying this same content. Step
            3 is already its own screen, so the panel (transfer volume, liquid
            class, rack numbers, row preview, excluded clones and the export
            itself) renders directly here now. */}
        <JanusMappingPanel />
      </div>
    </WizardContainer>
  );
}
