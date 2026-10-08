/**
 * ExportFormatSelector — Export All (Macrogen) single-form export.
 *
 * [source: spec §5 — "export.format: Export All single button"]
 *
 * Replaces the legacy two-section (IDT/Twist order + Plate Mapping) UI
 * with a single Export All form that calls handleExportAll(), which
 * invokes the kuro sidecar `export_all` RPC.
 *
 * Forward and reverse plate names are required before exporting.
 * Amount is either 0.05 or 0.2 μmole (Macrogen MOPC purification).
 * Echo and JANUS transfer volumes are independent fields.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { handleExportAll } from "@/components/layout/export-handlers";
import { PlateQuadrantPicker } from "@/components/widgets/PlateQuadrantPicker";
import { useKumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import type { AppState } from "@/store/appStore";
import { validateExportAll } from "@/store/validation";
import { localeIsKorean } from "@/lib/localeUtils";
import { MAX_MUTATIONS_PER_RUN } from "@/lib/inputThresholds";
import { useExportRounds } from "@/hooks/useExportRounds";
import {
  ECHO_QUADRANTS,
  echoPlacementIssue,
  HALF_LAYOUT_VERSION,
  QUADRANT_RESTORE_VERSION,
  quadrantColumnOffset,
} from "@/lib/echoQuadrant";
import {
  pickAt,
  plateOptionCount,
  roundPickIssue,
  usedBeforeRound,
  type PlateRound,
  type RoundPick,
} from "@/lib/plateRounds";
import type { EchoQuadrant } from "@/types/models";
const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;
const PROJECT_NAME_RE = /^[A-Za-z0-9가-힣_\-]{0,40}$/;
const ECHO_RANGE = { min: 25, max: 500, step: 1, unit: "nL" } as const;
const JANUS_RANGE = { min: 0.5, max: 10, step: 0.1, unit: "μL" } as const;

export function ExportFormatSelector() {
  const { t, i18n } = useTranslation();
  const tx = (key: string, fallback: string, vars?: Record<string, unknown>) =>
    t(key, { defaultValue: fallback, ...vars });
  const project = useKumaProject();
  const echoVol = useAppStore((s: AppState) => s.echoTransferVol);
  const echoQuadrant = useAppStore((s: AppState) => s.echoQuadrant);
  const setEchoQuadrant = useAppStore((s: AppState) => s.setEchoQuadrant);
  const echoUsedQuadrants = useAppStore((s: AppState) => s.echoUsedQuadrants);
  const setEchoUsedQuadrants = useAppStore((s: AppState) => s.setEchoUsedQuadrants);
  const echoLegacyPlacement = useAppStore((s: AppState) => s.echoLegacyPlacement);
  const janusVol = useAppStore((s: AppState) => s.janusTransferVol);
  const setEchoVol = useAppStore((s: AppState) => s.setEchoTransferVol);
  const setJanusVol = useAppStore((s: AppState) => s.setJanusTransferVol);
  const setRoundPicks = useAppStore((s: AppState) => s.setEchoRoundPicks);

  const { wellCount, roundMode, rounds, picks: roundPicks, picksStale } = useExportRounds();
  // A saved plate past the plates offered for this many rounds is unpicked in
  // `roundPicks`; write that back so the store, and the next save, agree.
  useEffect(() => {
    if (picksStale) setRoundPicks(roundPicks);
  }, [picksStale, roundPicks, setRoundPicks]);

  // The form fields are project state, kept in the store and the autosave
  // snapshot so leaving this step or reopening the project keeps them. Names
  // typed for a round the design no longer has stay in the store unshown and
  // unsent (only the current round labels are read below).
  const projectName = useAppStore((s: AppState) => s.exportName);
  const setProjectName = useAppStore((s: AppState) => s.setExportName);
  const plateNames = useAppStore((s: AppState) => s.exportPlateNames);
  const setPlateName = useAppStore((s: AppState) => s.setExportPlateName);
  const amount = useAppStore((s: AppState) => s.exportAmount);
  const setAmount = useAppStore((s: AppState) => s.setExportAmount);
  const vectormaps = useAppStore((s: AppState) => s.exportVectormaps);
  const setVectormaps = useAppStore((s: AppState) => s.setExportVectormaps);
  const nameGroups = roundMode
    ? rounds.map((round) => ({ key: round.label, count: round.to - round.from + 1 }))
    : [{ key: "single", count: wellCount }];
  const bom = useMemo(() => localeIsKorean(), [i18n.language]);
  const [running, setRunning] = useState(false);

  // PI 2026-05-15 (Item 2): plate name 빈칸 시각 표시는 유지하되 버튼은
  // 클릭 가능하다. 클릭 순간 toast.warning로 누락 항목을 안내한다. running 은
  // 여전히 hard disable (액션 불가 상태).
  const projectNameValid = PROJECT_NAME_RE.test(projectName);
  // Past one plate the selection is exported as rounds of one plate each,
  // however many that takes (`useExportRounds`). The split happens at the
  // design-to-mappings boundary, so export_all only ever receives one plate
  // per call.
  const canExport = !running && projectNameValid;

  // 사이드카가 거부하는 두 조합은 여기서 먼저 막는다. 넘기면 돌아오는 것은
  // 개발자용 영어 문장이고, 작업자가 할 일(round 고르기 또는 소진 표시 해제)은
  // 거기 없다.
  const placementIssue = echoPlacementIssue(echoQuadrant, echoUsedQuadrants);

  const onExport = async (roundIndex?: number) => {
    const round = roundIndex === undefined ? undefined : rounds[roundIndex];
    const { fwd: fwdPlate = "", rvs: rvsPlate = "" } = plateNames[round?.label ?? "single"] ?? {};
    // A round carries its own source plate and parity, picked on its own row
    // below, and starts from the earlier rounds on the same plate plus, on
    // plate 1, the parities marked as spent. Outside rounds the single picker
    // and its used-round checkboxes apply as before.
    const pick = round ? pickAt(roundPicks, roundIndex!) : undefined;
    const quadrant = pick ? pick.quadrant : echoQuadrant;
    const usedQuadrants = round
      ? usedBeforeRound(roundPicks, roundIndex!, echoUsedQuadrants)
      : echoUsedQuadrants;
    if (!round && placementIssue !== null) {
      toast.warning(t("validation.actionBlockedTitle"), {
        description: t(`phaseC.export.all.placementBlocked.${placementIssue}`),
      });
      return;
    }
    const roundIssue = round ? roundPickIssue(roundPicks, roundIndex!, echoUsedQuadrants) : null;
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
        description: check.missing.map((k) => t(k)).join("\n"),
      });
      return;
    }
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
        ...(round
          ? {
              round: {
                label: round.label,
                sourcePlate: pick!.plate!,
                mappings: round.mappings,
                dedupInfo: round.dedupInfo,
              },
            }
          : {}),
      });
      // toast surfacing handled inside handleExportAll
    } finally {
      setRunning(false);
    }
  };

  return (
    <section
      aria-labelledby="export-all-heading"
      className="flex flex-col gap-4 p-6"
    >
      <h3
        id="export-all-heading"
        className="text-sm font-semibold text-foreground"
      >
        {tx("phaseC.export.all.heading", "Export Package")}
      </h3>

      {/* Project name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="project-name"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.projectName", "Export name")}
        </label>
        <Input
          id="project-name"
          value={projectName}
          onChange={(e) => setProjectName(e.target.value)}
          placeholder={tx("phaseC.export.all.projectNamePlaceholder", "e.g. Q232A_K287R")}
          aria-invalid={!projectNameValid}
          aria-describedby="project-name-help"
          className={cn(!projectNameValid && "border-destructive")}
        />
        <span
          id="project-name-help"
          className="text-caption text-muted-foreground"
        >
          {tx("phaseC.export.all.projectNameHint", "Used as the export folder and file prefix. Leave empty to auto-name kuro_YYMMDD_HHMM.")}
        </span>
        {!projectNameValid && (
          <span role="alert" className="text-caption text-destructive">
            {tx(
              "phaseC.export.all.error.projectNameRegex",
              "Use up to 40 letters, numbers, Korean characters, underscores, or hyphens.",
            )}
          </span>
        )}
      </div>

      {nameGroups.map(({ key, count }) => {
        const { fwd: fwdPlate = "", rvs: rvsPlate = "" } = plateNames[key] ?? {};
        const fwdValid = fwdPlate === "" || PLATE_NAME_RE.test(fwdPlate);
        const rvsValid = rvsPlate === "" || PLATE_NAME_RE.test(rvsPlate);
        const suffix = roundMode ? `-${key}` : "";
        return (
          <div key={key} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <label
                htmlFor={`fwd-plate${suffix}`}
                className="text-sm font-medium text-foreground"
              >
                {tx("phaseC.export.all.plateNameFwd", "Forward primer plate name")}
                {roundMode && ` (${key})`}
              </label>
              <Input
                id={`fwd-plate${suffix}`}
                value={fwdPlate}
                onChange={(e) => setPlateName(key, "fwd", e.target.value)}
                placeholder="e.g. FWD_Plate_1"
                aria-describedby={`fwd-plate-help${suffix}`}
                className={cn(!fwdValid && "border-destructive")}
              />
              <span
                id={`fwd-plate-help${suffix}`}
                className="text-caption text-muted-foreground"
              >
                {tx("phaseC.export.all.wellCount", "{{count}} wells", { count })}
              </span>
              {!fwdValid && (
                <span role="alert" className="text-caption text-destructive">
                  {tx("phaseC.export.all.error.plateNameRegex", "Use 1-20 letters, numbers, underscores, or hyphens.")}
                </span>
              )}
            </div>

            {/* Reverse plate name */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor={`rvs-plate${suffix}`}
                className="text-sm font-medium text-foreground"
              >
                {tx("phaseC.export.all.plateNameRev", "Reverse primer plate name")}
                {roundMode && ` (${key})`}
              </label>
              <Input
                id={`rvs-plate${suffix}`}
                value={rvsPlate}
                onChange={(e) => setPlateName(key, "rvs", e.target.value)}
                placeholder="e.g. REV_Plate_1"
                className={cn(!rvsValid && "border-destructive")}
              />
              {!rvsValid && (
                <span role="alert" className="text-caption text-destructive">
                  {tx("phaseC.export.all.error.plateNameRegex", "Use 1-20 letters, numbers, underscores, or hyphens.")}
                </span>
              )}
            </div>

          </div>
        );
      })}

      {/* Order Vendor group: vendor header + Amount + Purification */}
      <div className="rounded-md border border-border p-3 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">
            {tx("phaseC.export.all.orderVendor", "Order vendor")}
          </span>
          <span className="text-xs text-muted-foreground">
            Macrogen Plate Oligo
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <label
              htmlFor="amount"
              className="text-sm font-medium text-foreground"
            >
              {tx("phaseC.export.all.amountLabel", "Amount")}
            </label>
            <select
              id="amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value as "0.05" | "0.2")}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring min-w-0"
            >
              <option value="0.05">0.05 μmole</option>
              <option value="0.2">0.2 μmole</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-foreground">
              {tx("phaseC.export.all.purificationLabel", "Purification")}
            </span>
            <span
              className="inline-flex items-center gap-1 px-3 py-1.5 text-sm text-muted-foreground"
              title={tx(
                "phaseC.export.all.purificationTooltip",
                "MOPC (Macrogen Oligo Purification Cartridge): Macrogen's standard purification method, not changeable.",
              )}
            >
              MOPC
              <Info
                className="h-3 w-3 text-muted-foreground"
                aria-hidden="true"
              />
            </span>
          </div>
        </div>
        <span className="text-caption text-muted-foreground block">
          {tx(
            "phaseC.export.all.orderVendorHint",
            "Included in Export all as a timestamp-prefixed Macrogen .xls file.",
          )}
        </span>
      </div>

      {/* Echo transfer volume */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="echo-vol"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.echoVolLabel", "Echo transfer volume")}
        </label>
        <div className="flex items-center gap-2">
          <Input
            id="echo-vol"
            type="number"
            min={ECHO_RANGE.min}
            max={ECHO_RANGE.max}
            step={ECHO_RANGE.step}
            value={echoVol}
            onChange={(e) => setEchoVol(Number(e.target.value))}
            className="w-28"
          />
          <span className="text-sm text-muted-foreground">{ECHO_RANGE.unit}</span>
        </div>
        <p className="text-caption text-muted-foreground">
          Range: {ECHO_RANGE.min}&ndash;{ECHO_RANGE.max} {ECHO_RANGE.unit}
          {echoVol > 500 && (
            <span className="ml-2 text-warning">
              ({Math.ceil(echoVol / 500)} transfers &times; &le;500 nL)
            </span>
          )}
        </p>
      </div>

      {/*
        Echo source plate 의 열 패리티. 96-head 는 한 번에 한 칸 건너 열에만
        닿으므로 한 round 가 홀수 열(A1 = 1, 3 .. 23) 또는 짝수 열(A2 = 2,
        4 .. 24)을 쓴다. reverse 는 같은 열에서 forward 바로 아래 행으로 간다.
        고르지 않으면 열을 건너뛰지 않는 기존 배치를 그대로 쓴다.
      */}
      {/* The notice points at the used-round checkboxes, shown in both modes. */}
      {echoLegacyPlacement !== null && (
        <p
          role="status"
          data-testid="echo-legacy-placement-notice"
          className="rounded-md border border-warning/40 bg-warning/10 p-2 text-caption text-foreground"
        >
          {t("phaseC.export.all.legacyPlacementNotice", {
            values: echoLegacyPlacement.join(", "),
            from: HALF_LAYOUT_VERSION,
            to: QUADRANT_RESTORE_VERSION,
          })}
        </p>
      )}
      {roundMode ? (
        <RoundPlatePicker
          rounds={rounds}
          wellCount={wellCount}
          picks={roundPicks}
          declaredUsed={echoUsedQuadrants}
          onDeclaredUsedChange={setEchoUsedQuadrants}
          onPick={(index, value) => {
            const next = rounds.map((_, k) => pickAt(roundPicks, k));
            next[index] = { ...next[index]!, ...value };
            setRoundPicks(next);
          }}
        />
      ) : (
        <PlateQuadrantPicker
          value={echoQuadrant}
          onChange={setEchoQuadrant}
          usedQuadrants={echoUsedQuadrants}
          onUsedQuadrantsChange={setEchoUsedQuadrants}
        />
      )}

      {/* JANUS transfer volume */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="janus-vol"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.janusVolLabel", "JANUS transfer volume")}
        </label>
        <div className="flex items-center gap-2">
          <Input
            id="janus-vol"
            type="number"
            min={JANUS_RANGE.min}
            max={JANUS_RANGE.max}
            step={JANUS_RANGE.step}
            value={janusVol}
            onChange={(e) => setJanusVol(Number(e.target.value))}
            className="w-28"
          />
          <span className="text-sm text-muted-foreground">{JANUS_RANGE.unit}</span>
        </div>
        <p className="text-caption text-muted-foreground">
          Range: {JANUS_RANGE.min}&ndash;{JANUS_RANGE.max} {JANUS_RANGE.unit}
        </p>
      </div>

      <p className="text-caption text-muted-foreground">
        {tx("phaseC.export.all.ruleHint", "Forward and reverse plate names are required.")}
      </p>

      {/* Per-clone GenBank maps, written to a sibling <prefix>_vectormaps/ folder. */}
      <div className="flex flex-col gap-1">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            id="export-vectormaps"
            checked={vectormaps}
            onChange={(e) => setVectormaps(e.target.checked)}
            className="h-3.5 w-3.5 accent-primary"
            aria-describedby="export-vectormaps-help"
          />
          <span className="text-foreground">
            {tx("phaseC.export.all.vectormapsLabel", "Also export a GenBank vector map per clone")}
          </span>
        </label>
        <span
          id="export-vectormaps-help"
          className="text-caption text-muted-foreground pl-5"
        >
          {tx(
            "phaseC.export.all.vectormapsHint",
            "Writes one .gb file per well, the parent vector with that clone's mutation marked, into a folder ending in {{folder}} next to the export folder. Needs a GenBank or SnapGene reference.",
            { folder: "_vectormaps" },
          )}
        </span>
      </div>

      {roundMode ? (
        <div className="flex flex-wrap gap-2">
          {rounds.map((round, index) => {
            const ready = roundPickIssue(roundPicks, index, echoUsedQuadrants) === null;
            return (
              <Button
                key={round.label}
                className="w-fit"
                disabled={!canExport || !ready}
                onClick={() => void onExport(index)}
              >
                {running
                  ? t("common.loading")
                  : t("phaseC.export.all.rounds.export", { round: index + 1 })}
              </Button>
            );
          })}
        </div>
      ) : (
        <Button
          className="w-fit"
          disabled={!canExport}
          onClick={() => void onExport()}
        >
          {running ? t("common.loading") : tx("phaseC.export.all.runExport", "Export all")}
        </Button>
      )}
    </section>
  );
}

/** Message for each reason a round cannot be exported yet. */
const ROUND_ISSUE_KEYS = {
  plateUnpicked: "phaseC.export.all.rounds.choosePlate",
  quadrantUnpicked: "phaseC.export.all.rounds.chooseFirst",
  duplicate: "phaseC.export.all.rounds.duplicate",
  quadrantAlreadyUsed: "phaseC.export.all.placementBlocked.quadrantAlreadyUsed",
} as const;

/**
 * One source-plate and one column-parity choice per export round, with no
 * default for either. The operator picks both because the plates may already
 * be part used, which this program cannot see. A parity another round has
 * taken on the same plate cannot be picked, and on plate 1 neither can one
 * marked as spent; the sidecar refuses both too (`check_quadrants_available`).
 * Plates past 1 are new plates, so the spent marks apply to plate 1 only.
 */
function RoundPlatePicker({
  rounds,
  wellCount,
  picks,
  declaredUsed,
  onDeclaredUsedChange,
  onPick,
}: {
  rounds: PlateRound[];
  wellCount: number;
  picks: readonly RoundPick[];
  declaredUsed: EchoQuadrant[];
  onDeclaredUsedChange: (value: EchoQuadrant[]) => void;
  onPick: (index: number, value: Partial<RoundPick>) => void;
}) {
  const { t } = useTranslation();
  const columns = (q: EchoQuadrant) =>
    t(
      quadrantColumnOffset(q) === 0
        ? "phaseC.export.all.quadrantColumnsOdd"
        : "phaseC.export.all.quadrantColumnsEven",
    );
  const plates = Array.from({ length: plateOptionCount(rounds.length) }, (_, k) => k + 1);
  const selectClass =
    "min-w-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";
  return (
    <div className="flex flex-col gap-2" data-testid="export-round-picker">
      <span className="text-sm font-medium text-foreground">
        {t("phaseC.export.all.quadrantLabel")}
      </span>
      <p className="text-caption text-muted-foreground">
        {t("phaseC.export.all.rounds.intro", {
          count: wellCount,
          rounds: rounds.length,
          perRound: MAX_MUTATIONS_PER_RUN,
        })}
      </p>
      {rounds.map((round, index) => {
        const pick = pickAt(picks, index);
        const taken = (q: EchoQuadrant) =>
          pick.plate !== null &&
          (picks.some((o, j) => j !== index && o.plate === pick.plate && o.quadrant === q) ||
            (pick.plate === 1 && declaredUsed.includes(q)));
        const issue = roundPickIssue(picks, index, declaredUsed);
        const id = `export-round-${round.label}`;
        return (
          <div key={round.label} className="flex flex-col gap-1">
            <span id={`${id}-label`} className="text-sm text-foreground">
              {t("phaseC.export.all.rounds.label", {
                round: index + 1,
                from: round.from,
                to: round.to,
              })}
            </span>
            <div className="flex flex-wrap gap-2">
              <select
                id={`${id}-plate`}
                aria-label={t("phaseC.export.all.rounds.plateSelect", { round: index + 1 })}
                value={pick.plate ?? ""}
                onChange={(e) =>
                  onPick(index, { plate: e.target.value === "" ? null : Number(e.target.value) })
                }
                className={selectClass}
              >
                <option value="" disabled>
                  {t("phaseC.export.all.rounds.choosePlateOption")}
                </option>
                {plates.map((n) => (
                  <option key={n} value={n}>
                    {t("phaseC.export.all.rounds.plateOption", { plate: n })}
                  </option>
                ))}
              </select>
              <select
                id={`${id}-parity`}
                aria-label={t("phaseC.export.all.rounds.paritySelect", { round: index + 1 })}
                value={pick.quadrant ?? ""}
                onChange={(e) =>
                  onPick(index, {
                    quadrant: e.target.value === "" ? null : (e.target.value as EchoQuadrant),
                  })
                }
                className={selectClass}
              >
                <option value="" disabled>
                  {t("phaseC.export.all.rounds.choose")}
                </option>
                {ECHO_QUADRANTS.map((q) => (
                  <option key={q} value={q} disabled={taken(q)}>
                    {`${q} (${columns(q)})`}
                  </option>
                ))}
              </select>
            </div>
            {(issue === "duplicate" || issue === "quadrantAlreadyUsed") && (
              <span role="alert" className="text-caption text-destructive">
                {t(ROUND_ISSUE_KEYS[issue])}
              </span>
            )}
          </div>
        );
      })}
      <div className="flex flex-col gap-1 mt-2">
        <span className="text-sm font-medium text-foreground">
          {t("phaseC.export.all.rounds.usedOnPlate1Label")}
        </span>
        <div className="flex flex-wrap gap-3">
          {ECHO_QUADRANTS.map((q) => (
            <label key={q} className="flex items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={declaredUsed.includes(q)}
                onChange={(e) =>
                  onDeclaredUsedChange(
                    e.target.checked
                      ? [...declaredUsed, q]
                      : declaredUsed.filter((x) => x !== q),
                  )
                }
              />
              {q}
            </label>
          ))}
        </div>
        <p className="text-caption text-muted-foreground">
          {t("phaseC.export.all.rounds.usedOnPlate1Helper")}
        </p>
      </div>
    </div>
  );
}
