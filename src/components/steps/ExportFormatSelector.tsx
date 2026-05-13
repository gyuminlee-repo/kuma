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
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { handleExportAll } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import type { AppState } from "@/store/appStore";

const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;
const ECHO_RANGE = { min: 25, max: 500, step: 1, unit: "nL" } as const;
const JANUS_RANGE = { min: 0.5, max: 10, step: 0.1, unit: "μL" } as const;
const WELL_LIMIT = 96;

export function ExportFormatSelector() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const designResults = useAppStore((s: AppState) => s.designResults);

  const wellCount = designResults.length;

  const [fwdPlate, setFwdPlate] = useState("");
  const [rvsPlate, setRvsPlate] = useState("");
  const [amount, setAmount] = useState<"0.05" | "0.2">("0.05");
  const [echoVol, setEchoVol] = useState(100);
  const [janusVol, setJanusVol] = useState(2.0);
  const [bom, setBom] = useState(false);
  const [running, setRunning] = useState(false);

  const fwdValid = fwdPlate === "" || PLATE_NAME_RE.test(fwdPlate);
  const rvsValid = rvsPlate === "" || PLATE_NAME_RE.test(rvsPlate);
  const wellOverflow = wellCount > WELL_LIMIT;
  const canExport = fwdValid && rvsValid && !wellOverflow && !running && wellCount > 0;

  const onExport = async () => {
    setRunning(true);
    try {
      await handleExportAll({
        projectId: project?.project_id,
        fwdPlateName: fwdPlate || undefined,
        rvsPlateName: rvsPlate || undefined,
        amount,
        echoTransferVol: echoVol,
        janusTransferVol: janusVol,
        bom,
      });
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
        {t("phaseC.export.all.heading")}
      </h3>

      {/* Forward plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="fwd-plate"
          className="text-sm font-medium text-foreground"
        >
          {t("phaseC.export.all.plateNameFwd")}
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
          {t("phaseC.export.all.wellCount", { count: wellCount })}
        </span>
        {!fwdValid && (
          <span role="alert" className="text-caption text-destructive">
            {t("phaseC.export.all.error.plateNameRegex")}
          </span>
        )}
        {wellOverflow && (
          <span role="alert" className="text-caption text-destructive">
            {t("phaseC.export.all.error.wellOverflow", { count: wellCount })}
          </span>
        )}
      </div>

      {/* Reverse plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="rvs-plate"
          className="text-sm font-medium text-foreground"
        >
          {t("phaseC.export.all.plateNameRev")}
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
            {t("phaseC.export.all.error.plateNameRegex")}
          </span>
        )}
      </div>

      {/* Amount */}
      <div className="flex flex-col gap-1">
        <label htmlFor="amount" className="text-sm font-medium text-foreground">
          {t("phaseC.export.all.amountLabel")}
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
            {t("phaseC.export.all.purificationLabel")}: MOPC
          </span>
        </div>
      </div>

      {/* Echo transfer volume */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="echo-vol"
          className="text-sm font-medium text-foreground"
        >
          {t("phaseC.export.all.echoVolLabel")}
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
          {t("phaseC.export.all.janusVolLabel")}
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
          {t("phaseC.export.all.bomLabel")}
          <span className="ml-1 text-muted-foreground">
            {t("phaseC.export.all.bomHint")}
          </span>
        </label>
      </div>

      <p className="text-caption text-muted-foreground">
        {t("phaseC.export.all.ruleHint")}
      </p>

      <Button
        className="w-fit"
        disabled={!canExport}
        onClick={() => void onExport()}
      >
        {running ? t("common.loading") : t("phaseC.export.all.runExport")}
      </Button>
    </section>
  );
}
