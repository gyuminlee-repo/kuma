import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/button";
import { localeIsKorean } from "../../lib/localeUtils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Input } from "../ui/input";

interface MappingExportDialogProps {
  open: boolean;
  initialFormat?: "echo" | "janus";
  onOpenChange: (open: boolean) => void;
  onExport: (params: { format: "echo" | "janus"; transferVol: number; bom: boolean }) => void;
}

type MappingFormat = "echo" | "janus";

const FORMAT_DEFAULTS: Record<
  MappingFormat,
  { transferVol: number; unit: string; min: number; max: number; step: number }
> = {
  echo: { transferVol: 100, unit: "nL", min: 25, max: 500, step: 1 },
  janus: { transferVol: 2.0, unit: "µL", min: 0.5, max: 10, step: 0.1 },
};

export function MappingExportDialog({
  open,
  initialFormat = "echo",
  onOpenChange,
  onExport,
}: MappingExportDialogProps) {
  const { t } = useTranslation();
  const [format, setFormat] = useState<"echo" | "janus">(initialFormat);
  const cfg = FORMAT_DEFAULTS[format];
  const [transferVol, setTransferVol] = useState<number>(cfg.transferVol);
  const [bom, setBom] = useState<boolean>(localeIsKorean());

  // Apply initial format when opened; reset transferVol when format changes.
  useEffect(() => {
    if (open) setFormat(initialFormat);
  }, [open, initialFormat]);

  useEffect(() => {
    setTransferVol(FORMAT_DEFAULTS[format].transferVol);
  }, [format]);

  function handleExportClick() {
    onExport({ format, transferVol, bom });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">{format === "echo" ? t("mappingExportDialog.titleEcho") : t("mappingExportDialog.titleJanus")}</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            {t("mappingExportDialog.descriptionFiles")}
            <br />
            <span className="text-muted-foreground">.xlsx</span> — human-readable layout preview
            <br />
            <span className="text-muted-foreground">.csv</span> — machine input (actual liquid-handler upload)
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Machine Format */}
          <div className="flex flex-col gap-2 rounded-container border border-border bg-card p-4">
            <label className="text-sm font-medium text-foreground">
              {t("mappingExportDialog.machineLabel")}
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={format === "echo" ? "default" : "outline"}
                className="rounded-full"
                onClick={() => setFormat("echo")}
                type="button"
              >
                Echo 525
              </Button>
              <Button
                size="sm"
                variant={format === "janus" ? "default" : "outline"}
                className="rounded-full"
                onClick={() => setFormat("janus")}
                type="button"
              >
                JANUS
              </Button>
            </div>
          </div>

          {/* Transfer Volume */}
          <div className="flex flex-col gap-2 rounded-container border border-border bg-card p-4">
            <label className="text-sm font-medium text-foreground">
              {t("mappingExportDialog.transferVolumeLabel")}
            </label>
            <div className="flex items-center gap-2">
              <Input
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
              {t("mappingExportDialog.transferVolumeRange", {
                min: cfg.min,
                max: cfg.max,
                unit: cfg.unit,
              })}
              {format === "echo" && (
                <span className="ml-2 font-medium text-foreground">
                  {t("mappingExportDialog.echoMaxNote")}
                </span>
              )}
            </p>
          </div>
        </div>

          {/* BOM option */}
          <div className="flex items-center gap-2 rounded-container border border-border bg-card px-4 py-3">
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
              <span className="ml-1 text-muted-foreground">{t("mappingExportDialog.bomCheckboxHint")}</span>
            </label>
          </div>

        <DialogFooter>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full"
            onClick={() => onOpenChange(false)}
            type="button"
          >
            {t("mappingExportDialog.cancelBtn")}
          </Button>
          <Button size="sm" className="rounded-full" onClick={handleExportClick} type="button">
            {t("mappingExportDialog.exportBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
