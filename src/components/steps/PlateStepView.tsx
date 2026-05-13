/**
 * PlateStepView — "plate" major step 단일 페이지.
 *
 * [source: spec Phase F §2 — F2 PlateStepView WizardContainer + Export All footer]
 *
 * WizardContainer로 감싸며 Next 버튼이 Export All (MappingExportDialog) 역할을 한다.
 * exportDialogOpen state와 MappingExportDialog 마운트를 PlateMap에서 여기로 이동.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { PlateMap } from "@/components/widgets/PlateMap";
import { WizardContainer } from "@/components/steps/WizardContainer";
import { MappingExportDialog } from "@/components/dialogs/MappingExportDialog";
import { handleExportAll, handleExportMappingWithParams } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";

export function PlateStepView() {
  const { t } = useTranslation();
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const project = useKumaProject();
  const goToPrevStep = useAppStore((s) => s.goToPrevStep);
  const hasPlate = useAppStore((s) => s.plateMappings.length > 0);

  function handleExportAllClick() {
    if (!project || project.scratch || !project.path) {
      toast.error(t("plateMap.exportAllTitle"));
      return;
    }
    setExportDialogOpen(true);
  }

  return (
    <WizardContainer
      stepIndex={1}
      stepTotal={1}
      titleKey="phaseC.subSteps.plate.layout"
      descriptionKey="phaseE.descriptions.plate.layout"
      onPrev={() => goToPrevStep()}
      onNext={hasPlate ? handleExportAllClick : undefined}
      nextLabelKey="plateMap.exportAll"
    >
      <PlateMap />

      <MappingExportDialog
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        onExport={async ({ format, transferVol, bom }) => {
          setExportDialogOpen(false);
          try {
            await handleExportMappingWithParams(format, { transferVol, bom });
            await handleExportAll(project);
            toast.success(t("plateMap.exportAllComplete"));
          } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            toast.error(t("plateMap.exportAllFailed", { message: msg }));
          }
        }}
      />
    </WizardContainer>
  );
}
