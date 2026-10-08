import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { handleExportAll } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import { validateExportAll } from "@/store/validation";
import { localeIsKorean } from "@/lib/localeUtils";
import { echoPlacementIssue } from "@/lib/echoQuadrant";
import { useExportRounds } from "@/hooks/useExportRounds";
import { pickAt, roundPickIssue, usedBeforeRound } from "@/lib/plateRounds";
import { PLATE_NAME_RE, PROJECT_NAME_RE, ROUND_ISSUE_KEYS } from "./exportSettings";

/** Final action, after the operator has reviewed the export layout and order. */
export function ExportAction() {
  const { t, i18n } = useTranslation();
  const project = useKumaProject();
  const projectName = useAppStore((s) => s.exportName);
  const plateNames = useAppStore((s) => s.exportPlateNames);
  const amount = useAppStore((s) => s.exportAmount);
  const vectormaps = useAppStore((s) => s.exportVectormaps);
  const echoVol = useAppStore((s) => s.echoTransferVol);
  const janusVol = useAppStore((s) => s.janusTransferVol);
  const echoQuadrant = useAppStore((s) => s.echoQuadrant);
  const echoUsedQuadrants = useAppStore((s) => s.echoUsedQuadrants);
  const { wellCount, roundMode, rounds, picks: roundPicks } = useExportRounds();
  const bom = useMemo(() => localeIsKorean(), [i18n.language]);
  const [running, setRunning] = useState(false);
  // State disables the UI; the ref also blocks a second click before React
  // commits that render, including while the destination dialog is pending.
  const pending = useRef(false);
  const projectNameValid = PROJECT_NAME_RE.test(projectName);
  const canExport = !running && projectNameValid;
  const placementIssue = echoPlacementIssue(echoQuadrant, echoUsedQuadrants);

  const onExport = async (roundIndex?: number) => {
    if (pending.current || !projectNameValid) return;
    const round = roundIndex === undefined ? undefined : rounds[roundIndex];
    // Never fall back to the unsplit export for an absent round.
    if (roundMode && (roundIndex === undefined || !round)) return;
    const { fwd: fwdPlate = "", rvs: rvsPlate = "" } = plateNames[round?.label ?? "single"] ?? {};
    const pick = roundIndex === undefined ? undefined : pickAt(roundPicks, roundIndex);
    const quadrant = pick ? pick.quadrant : echoQuadrant;
    const usedQuadrants = roundIndex === undefined
      ? echoUsedQuadrants
      : usedBeforeRound(roundPicks, roundIndex, echoUsedQuadrants);
    if (!round && placementIssue !== null) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: t(`phaseC.export.all.placementBlocked.${placementIssue}`),
      });
      return;
    }
    const roundIssue = roundIndex === undefined
      ? null
      : roundPickIssue(roundPicks, roundIndex, echoUsedQuadrants);
    if (roundIssue !== null) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: t(ROUND_ISSUE_KEYS[roundIssue]),
      });
      return;
    }
    const check = validateExportAll({
      fwdPlate,
      rvsPlate,
      wellCount,
      plateNameRe: PLATE_NAME_RE,
    });
    if (!check.ok) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: check.missing.map((key) => t(key)).join("\n"),
      });
      return;
    }
    const sourcePlate = pick?.plate;
    if (round && sourcePlate == null) return;
    pending.current = true;
    setRunning(true);
    try {
      await handleExportAll({
        projectId: project?.project_id,
        projectPath: project?.path,
        projectName: projectName || undefined,
        fwdPlateName: fwdPlate || undefined,
        rvsPlateName: rvsPlate || undefined,
        amount,
        echoTransferVol: echoVol,
        janusTransferVol: janusVol,
        bom,
        quadrant,
        usedQuadrants,
        vectormaps,
        ...(round && sourcePlate != null
          ? {
              round: {
                label: round.label,
                sourcePlate,
                mappings: round.mappings,
                dedupInfo: round.dedupInfo,
              },
            }
          : {}),
      });
      // Success, partial success and RPC failure toasts stay in the handler.
    } catch (error) {
      // The destination dialog can reject before the handler's RPC try/catch.
      toast.error(t("phaseC.export.all.exportError", { defaultValue: "Export failed" }), {
        description: error instanceof Error ? error.message : String(error),
        duration: 8000,
      });
    } finally {
      pending.current = false;
      setRunning(false);
    }
  };

  // Missing names/results remain clickable so the existing validation toast
  // can explain what is needed. Invalid export names and pending work disable.
  return (
    <div className="flex flex-wrap justify-end gap-2 p-6" data-testid="export-action">
      {roundMode ? rounds.map((round, index) => (
        <Button
          key={round.label}
          className="w-fit"
          disabled={!canExport || roundPickIssue(roundPicks, index, echoUsedQuadrants) !== null}
          onClick={() => void onExport(index)}
        >
          {running
            ? t("common.loading")
            : t("phaseC.export.all.rounds.export", { round: index + 1 })}
        </Button>
      )) : (
        <Button className="w-fit" disabled={!canExport} onClick={() => void onExport()}>
          {running
            ? t("common.loading")
            : t("phaseC.export.all.runExport", { defaultValue: "Export" })}
        </Button>
      )}
    </div>
  );
}
