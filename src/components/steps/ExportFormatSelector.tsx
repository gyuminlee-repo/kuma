/**
 * ExportFormatSelector — IDT CSV / Twist CSV / FASTA export buttons.
 *
 * [source: spec §1 — "export.format: IDT CSV / Twist CSV / FASTA 선택"]
 *
 * Uses existing export-handlers (handleExportExcel) for IDT/Twist CSV.
 * FASTA export deferred to Stage 3.
 *
 * TODO Stage 3: consolidate with MenuBar File > Export removal (spec §0 결정사항).
 * TODO Stage 3: wire FASTA format to handleOpenSequence or dedicated FASTA export.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { handleExportExcel } from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";

export type ExportFormat = "idt" | "twist" | "fasta";

const FORMATS: { value: ExportFormat; labelKey: string }[] = [
  { value: "idt",   labelKey: "phaseC.export.format.idt" },
  { value: "twist", labelKey: "phaseC.export.format.twist" },
  { value: "fasta", labelKey: "phaseC.export.format.fasta" },
];

export function ExportFormatSelector() {
  const { t } = useTranslation();
  const [format, setFormat] = useState<ExportFormat>("idt");
  const [isExporting, setIsExporting] = useState(false);
  const project = useKumaProject();

  const handleExport = async () => {
    setIsExporting(true);
    try {
      if (format === "idt" || format === "twist") {
        await handleExportExcel(project?.project_id);
      }
      // format === "fasta": TODO Stage 3 — wire FASTA export
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      className="flex flex-col gap-6 p-6"
      role="region"
      aria-label={t("phaseC.subSteps.export.format")}
    >
      <h3 className="text-sm font-semibold text-foreground">
        {t("phaseC.subSteps.export.format")}
      </h3>
      <div
        role="radiogroup"
        aria-label={t("phaseC.subSteps.export.format")}
        className="flex flex-col gap-3"
      >
        {FORMATS.map((fmt) => (
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
        onClick={() => void handleExport()}
        disabled={isExporting}
      >
        {isExporting ? t("common.loading") : t("phaseC.export.runExport")}
      </Button>
    </div>
  );
}
