/**
 * ExportFormatSelector — two export sections on the export.format sub-step.
 *
 * [source: spec §1 — "export.format: IDT CSV / Twist CSV / FASTA 선택"]
 *
 * Section 1 — Primer Order Export: IDT CSV / Twist CSV / FASTA
 *   Uses handleExportExcel for IDT/Twist CSV.
 *
 * Section 2 — Plate Mapping Export: Echo / JANUS
 *   Inline form that reuses handleExportMappingWithParams, replacing the
 *   dead MenuBar MappingExportDialog that was removed in Phase C follow-up.
 *   PlateMap.tsx still mounts its own dialog (preserved, not touched).
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { handleExportExcel, handleExportMappingWithParams } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";

export type ExportFormat = "idt" | "twist" | "fasta";
type MappingFormat = "echo" | "janus";

const ORDER_FORMATS: { value: ExportFormat; labelKey: string }[] = [
  { value: "idt",   labelKey: "phaseC.export.format.idt" },
  { value: "twist", labelKey: "phaseC.export.format.twist" },
  { value: "fasta", labelKey: "phaseC.export.format.fasta" },
];

const MAPPING_FORMAT_DEFAULTS: Record<
  MappingFormat,
  { transferVol: number; unit: string; min: number; max: number; step: number }
> = {
  echo:  { transferVol: 100, unit: "nL", min: 50, max: 5000, step: 1 },
  janus: { transferVol: 2.0, unit: "µL", min: 0.5, max: 10, step: 0.1 },
};

export function ExportFormatSelector() {
  const { t } = useTranslation();
  const project = useKumaProject();

  // --- Primer order section ---
  const [format, setFormat] = useState<ExportFormat>("idt");
  const [isExporting, setIsExporting] = useState(false);

  // --- Plate mapping section ---
  const [mappingFormat, setMappingFormat] = useState<MappingFormat>("echo");
  const cfg = MAPPING_FORMAT_DEFAULTS[mappingFormat];
  const [transferVol, setTransferVol] = useState<number>(cfg.transferVol);
  const [bom, setBom] = useState<boolean>(false);
  const [isMappingExporting, setIsMappingExporting] = useState(false);

  // Reset transferVol when mapping format changes
  useEffect(() => {
    setTransferVol(MAPPING_FORMAT_DEFAULTS[mappingFormat].transferVol);
  }, [mappingFormat]);

  const handleOrderExport = async () => {
    setIsExporting(true);
    try {
      if (format === "idt" || format === "twist") {
        await handleExportExcel(project?.project_id);
      }
      // format === "fasta": TODO wire FASTA export
    } finally {
      setIsExporting(false);
    }
  };

  const handleMappingExport = async () => {
    setIsMappingExporting(true);
    try {
      await handleExportMappingWithParams(mappingFormat, { transferVol, bom });
    } finally {
      setIsMappingExporting(false);
    }
  };

  return (
    <div
      className="flex flex-col gap-8 p-6"
      role="region"
      aria-label={t("phaseC.subSteps.export.format")}
    >
      {/* ── Section 1: Primer Order Export ── */}
      <section aria-labelledby="order-export-heading">
        <h3
          id="order-export-heading"
          className="mb-4 text-sm font-semibold text-foreground"
        >
          {t("phaseC.export.orderExport.heading")}
        </h3>
        <div
          role="radiogroup"
          aria-label={t("phaseC.export.orderExport.heading")}
          className="flex flex-col gap-3 mb-4"
        >
          {ORDER_FORMATS.map((fmt) => (
            <label
              key={fmt.value}
              className={cn(
                "flex items-center gap-2 cursor-pointer text-sm",
                format === fmt.value ? "text-foreground" : "text-muted-foreground",
              )}
            >
              <input
                type="radio"
                name="export-format"
                value={fmt.value}
                checked={format === fmt.value}
                onChange={() => setFormat(fmt.value)}
                className="accent-primary"
              />
              {t(fmt.labelKey)}
            </label>
          ))}
        </div>
        <Button
          className="w-fit"
          onClick={() => void handleOrderExport()}
          disabled={isExporting}
        >
          {isExporting ? t("common.loading") : t("phaseC.export.runExport")}
        </Button>
      </section>

      <hr className="border-border" />

      {/* ── Section 2: Plate Mapping Export ── */}
      <section aria-labelledby="mapping-export-heading">
        <h3
          id="mapping-export-heading"
          className="mb-4 text-sm font-semibold text-foreground"
        >
          {t("phaseC.export.mappingExport.heading")}
        </h3>

        {/* Machine format toggle */}
        <div className="flex flex-col gap-2 rounded-container border border-border bg-card p-4 mb-3">
          <span className="text-sm font-medium text-foreground">
            {t("mappingExportDialog.machineLabel")}
          </span>
          <div
            role="radiogroup"
            aria-label={t("mappingExportDialog.machineLabel")}
            className="flex gap-2"
          >
            {(["echo", "janus"] as const).map((mf) => (
              <label key={mf} className="flex items-center gap-1 cursor-pointer text-sm">
                <input
                  type="radio"
                  name="mapping-format"
                  value={mf}
                  checked={mappingFormat === mf}
                  onChange={() => setMappingFormat(mf)}
                  className="accent-primary"
                />
                {mf === "echo" ? "Echo 525" : "JANUS"}
              </label>
            ))}
          </div>
        </div>

        {/* Transfer volume */}
        <div className="flex flex-col gap-2 rounded-container border border-border bg-card p-4 mb-3">
          <label
            htmlFor="mapping-transfer-vol"
            className="text-sm font-medium text-foreground"
          >
            {t("mappingExportDialog.transferVolumeLabel")}
          </label>
          <div className="flex items-center gap-2">
            <Input
              id="mapping-transfer-vol"
              type="number"
              min={cfg.min}
              max={cfg.max}
              step={cfg.step}
              value={transferVol}
              onChange={(e) => setTransferVol(Number(e.target.value))}
              className="w-28"
            />
            <span className="text-sm text-muted-foreground">{cfg.unit}</span>
          </div>
          <p className="text-caption text-muted-foreground">
            Range: {cfg.min}&ndash;{cfg.max} {cfg.unit}
            {mappingFormat === "echo" && transferVol > 500 && (
              <span className="ml-2 text-warning">
                ({Math.ceil(transferVol / 500)} transfers &times; &le;500 nL)
              </span>
            )}
          </p>
        </div>

        {/* BOM checkbox */}
        <div className="flex items-center gap-2 rounded-container border border-border bg-card px-4 py-3 mb-4">
          <input
            id="mapping-bom-checkbox"
            type="checkbox"
            checked={bom}
            onChange={(e) => setBom(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-primary cursor-pointer"
            aria-label={t("mappingExportDialog.bomCheckboxAriaLabel")}
          />
          <label
            htmlFor="mapping-bom-checkbox"
            className="text-sm text-foreground cursor-pointer select-none"
          >
            {t("mappingExportDialog.bomCheckboxLabel")}
            <span className="ml-1 text-muted-foreground">
              {t("mappingExportDialog.bomCheckboxHint")}
            </span>
          </label>
        </div>

        <Button
          className="w-fit"
          onClick={() => void handleMappingExport()}
          disabled={isMappingExporting}
        >
          {isMappingExporting
            ? t("common.loading")
            : t("phaseC.export.mappingExport.runExport")}
        </Button>
      </section>
    </div>
  );
}
