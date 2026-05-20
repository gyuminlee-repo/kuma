/**
 * ExportFormatSelector — Export All (Macrogen) single-form export.
 *
 * [source: spec §5 — "export.format: Export All single button"]
 *
 * Replaces the legacy two-section (IDT/Twist order + Plate Mapping) UI
 * with a single Export All form that calls handleExportAll(), which
 * invokes the kuro sidecar `export_all` RPC.
 *
 * Plate names are optional; if empty, the sidecar uses a default name.
 * Amount is either 0.05 or 0.2 μmole (Macrogen MOPC purification).
 * Echo and JANUS transfer volumes are independent fields.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { handleExportAll } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import type { AppState } from "@/store/appStore";
import { validateExportAll } from "@/store/validation";

const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;
const PROJECT_NAME_RE = /^[A-Za-z0-9가-힣_\-]{0,40}$/;
const ECHO_RANGE = { min: 25, max: 500, step: 1, unit: "nL" } as const;
const JANUS_RANGE = { min: 0.5, max: 10, step: 0.1, unit: "μL" } as const;
const WELL_LIMIT = 96;

export function ExportFormatSelector() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string, vars?: Record<string, unknown>) =>
    t(key, { defaultValue: fallback, ...vars });
  const project = useKumaProject();
  const designResults = useAppStore((s: AppState) => s.designResults);
  const echoVol = useAppStore((s: AppState) => s.echoTransferVol);
  const janusVol = useAppStore((s: AppState) => s.janusTransferVol);
  const setEchoVol = useAppStore((s: AppState) => s.setEchoTransferVol);
  const setJanusVol = useAppStore((s: AppState) => s.setJanusTransferVol);

  const wellCount = designResults.length;

  const [projectName, setProjectName] = useState("");
  const [fwdPlate, setFwdPlate] = useState("");
  const [rvsPlate, setRvsPlate] = useState("");
  const [orderVendor, setOrderVendor] = useState<"macrogen">("macrogen");
  const [amount, setAmount] = useState<"0.05" | "0.2">("0.05");
  const [bom, setBom] = useState(false);
  const [running, setRunning] = useState(false);

  // PI 2026-05-15 (Item 2): plate name 빈칸 시각 표시는 유지하되 버튼은
  // 클릭 가능 — 클릭 순간 toast.warning로 누락 항목 안내. wellOverflow / running은
  // 여전히 hard disable (액션 불가 상태).
  const fwdValid = fwdPlate === "" || PLATE_NAME_RE.test(fwdPlate);
  const rvsValid = rvsPlate === "" || PLATE_NAME_RE.test(rvsPlate);
  const projectNameValid = PROJECT_NAME_RE.test(projectName);
  const wellOverflow = wellCount > WELL_LIMIT;
  const canExport = !wellOverflow && !running && projectNameValid;

  const onExport = async () => {
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
        projectName: projectName || undefined,
        fwdPlateName: fwdPlate || undefined,
        rvsPlateName: rvsPlate || undefined,
        amount,
        echoTransferVol: echoVol,
        janusTransferVol: janusVol,
        bom,
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

      {/* Forward plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="fwd-plate"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.plateNameFwd", "Forward primer plate name")}
        </label>
        <Input
          id="fwd-plate"
          value={fwdPlate}
          onChange={(e) => setFwdPlate(e.target.value)}
          placeholder="e.g. FWD_Plate_1"
          aria-describedby="fwd-plate-help"
          className={cn(!fwdValid && "border-destructive")}
        />
        <span
          id="fwd-plate-help"
          className="text-caption text-muted-foreground"
        >
          {tx("phaseC.export.all.wellCount", "{{count}} wells", { count: wellCount })}
        </span>
        {!fwdValid && (
          <span role="alert" className="text-caption text-destructive">
            {tx("phaseC.export.all.error.plateNameRegex", "Use 1-20 letters, numbers, underscores, or hyphens.")}
          </span>
        )}
        {wellOverflow && (
          <span role="alert" className="text-caption text-destructive">
            {tx("phaseC.export.all.error.wellOverflow", "{{count}} wells exceed one 96-well plate.", { count: wellCount })}
          </span>
        )}
      </div>

      {/* Reverse plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="rvs-plate"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.plateNameRev", "Reverse primer plate name")}
        </label>
        <Input
          id="rvs-plate"
          value={rvsPlate}
          onChange={(e) => setRvsPlate(e.target.value)}
          placeholder="e.g. REV_Plate_1"
          className={cn(!rvsValid && "border-destructive")}
        />
        {!rvsValid && (
          <span role="alert" className="text-caption text-destructive">
            {tx("phaseC.export.all.error.plateNameRegex", "Use 1-20 letters, numbers, underscores, or hyphens.")}
          </span>
        )}
      </div>

      {/* Order vendor */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="order-vendor"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.all.orderVendor", "Order vendor")}
        </label>
        <select
          id="order-vendor"
          value={orderVendor}
          onChange={(e) => setOrderVendor(e.target.value as "macrogen")}
          className="w-fit rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring min-w-0"
        >
          <option value="macrogen">Macrogen</option>
        </select>
        <span className="text-caption text-muted-foreground">
          {tx("phaseC.export.all.orderVendorHint", "Included in Export all as a timestamp-prefixed Macrogen .xls file.")}
        </span>
      </div>

      {/* Amount */}
      <div className="flex flex-col gap-1">
        <label htmlFor="amount" className="text-sm font-medium text-foreground">
          {tx("phaseC.export.all.amountLabel", "Amount")}
        </label>
        <div className="flex items-center gap-3">
          <select
            id="amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value as "0.05" | "0.2")}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring min-w-0"
          >
            <option value="0.05">0.05 μmole</option>
            <option value="0.2">0.2 μmole</option>
          </select>
          <span className="text-sm text-muted-foreground">
            {tx("phaseC.export.all.purificationLabel", "Purification")}: MOPC
          </span>
        </div>
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

      {/* BOM checkbox */}
      <div className="flex items-center gap-2 rounded-container border border-border bg-card px-4 py-3">
        <input
          id="bom-checkbox"
          type="checkbox"
          checked={bom}
          onChange={(e) => setBom(e.target.checked)}
          className="h-4 w-4 rounded border-border accent-primary cursor-pointer"
        />
        <label
          htmlFor="bom-checkbox"
          className="text-sm text-foreground cursor-pointer select-none"
        >
          {tx("phaseC.export.all.bomLabel", "Include BOM")}
          <span className="ml-1 text-muted-foreground">
            {tx("phaseC.export.all.bomHint", "(bill of materials)")}
          </span>
        </label>
      </div>

      <p className="text-caption text-muted-foreground">
        {tx("phaseC.export.all.ruleHint", "Plate names are optional. Empty names use backend defaults.")}
      </p>

      <Button
        className="w-fit"
        disabled={!canExport}
        onClick={() => void onExport()}
      >
        {running ? t("common.loading") : tx("phaseC.export.all.runExport", "Export all")}
      </Button>
    </section>
  );
}
