/**
 * JanusStepView — "janus" mame phase, step 3.1 (Janus instrument settings).
 *
 * The instrument configuration used to sit inside step 2.1 (inputs), which made
 * an operator who only wants a sequencing verdict walk past a cell-picking robot
 * they are not going to use. It is its own major step now: step 2 ends at the
 * verdict, step 3 is the instrument, step 4 is the activity data.
 *
 * The step stays optional in the strict sense: nothing here gates a run and
 * nothing downstream gates on it. An analyze run writes `..._picks.csv` and
 * `..._janus.csv` on its own from whatever is stored, so skipping this step
 * costs the liquid class (which ships blank) and nothing else.
 *
 * What lives here:
 *   - transfer volume, the one instrument value nothing can derive
 *   - the deck reference, so the plate names on screen are the ones the JANUS
 *     software matches
 *   - the settings/export dialog (deck rack numbers, liquid class, row preview,
 *     excluded clones, and the mapping export itself)
 *   - what the last run did with the two files it writes
 */

import { useState } from "react";
import { Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { Button } from "@/components/ui/button";
import { JanusMappingDialog } from "@/components/mame/dialogs/JanusMappingDialog";
import { JanusDeckPreview } from "@/components/mame/widgets/JanusDeckPreview";
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
  const [dialogOpen, setDialogOpen] = useState(false);

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
            class (left blank when unset). It sits on the step rather than only
            in the dialog because the run writes the instrument sheet on its
            own, and the shipped 100 µL is an assumption with no lab source. */}
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

        {/* The dialog carries the deck rack numbers, the liquid class, the row
            preview, the excluded clones and the export. Enabled before a run
            too, so the values can be prepared in advance. */}
        <div className="max-w-sm space-y-1">
          <Button
            variant="outline"
            size="sm"
            className="h-control w-full gap-1.5 rounded-control text-caption"
            onClick={() => setDialogOpen(true)}
            aria-label={t("mame.janus.settings.openDialogAriaLabel")}
          >
            <Settings2 size={12} aria-hidden="true" />
            {t("mame.janus.settings.openDialog")}
          </Button>
          <p className="text-caption text-muted-foreground">
            {t("mame.janus.settings.dialogHint")}
          </p>
        </div>

        {/* What the last run did with the two files it writes itself. */}
        <JanusAutosaveNotice />

        <JanusDeckPreview className="max-w-xl" />

        <JanusMappingDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      </div>
    </WizardContainer>
  );
}
