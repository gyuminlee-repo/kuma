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
 *   - transfer volume, the one instrument value nothing can derive
 *   - the deck reference, so the plate names on screen are the ones the JANUS
 *     software matches
 *   - the mapping panel (deck rack numbers, liquid class, row preview, excluded
 *     clones, and the mapping export itself). Used to be a dialog opened from a
 *     button here; step 3 is already a dedicated screen, so it is inlined now.
 *   - what the last run did with the pick list it writes automatically
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
  const janusSettings = useMameAppStore((s) => s.janusSettings);
  const setJanusSettings = useMameAppStore((s) => s.setJanusSettings);

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

        {/* Transfer volume, the one instrument value nothing can derive: how
            much of a cell stock to move is an experimental condition, unlike
            the deck numbers (taken from the plates of the run) and the liquid
            class (left blank when unset). The shipped 100 µL is an assumption
            with no lab source, so it is set here rather than left as a hidden
            default the export panel just inherits. */}
        <div className="max-w-sm space-y-1">
          <label
            htmlFor="mame-janus-volume"
            className="text-caption font-medium text-muted-foreground"
          >
            {t("mame.janus.settings.volumeLabel")}
          </label>
          <input
            id="mame-janus-volume"
            type="number"
            min={0}
            step="any"
            value={janusSettings.volume}
            onChange={(e) => {
              const parsed = Number.parseFloat(e.target.value);
              if (Number.isFinite(parsed) && parsed > 0) {
                setJanusSettings({ ...janusSettings, volume: parsed });
              }
            }}
            className="h-control w-full rounded-control border border-border bg-background px-2 text-caption"
          />
          <p className="text-caption text-muted-foreground">
            {t("mame.janus.settings.volumeHint")}
          </p>
        </div>

        {/* What the last run did with the pick list it writes itself. The
            instrument mapping has no autosave notice: it is only ever
            written by the export button below, so there is nothing
            automatic to report on. */}
        <JanusAutosaveNotice />

        {/* Was a button that opened a modal carrying this same content. Step
            3 is already its own screen, so the panel (deck preview, rack
            numbers, liquid class, row preview, excluded clones and the
            export itself) renders directly here now. */}
        <JanusMappingPanel />
      </div>
    </WizardContainer>
  );
}
