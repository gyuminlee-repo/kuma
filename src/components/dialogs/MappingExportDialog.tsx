import { useEffect, useState } from "react";
import { Button } from "../ui/button";
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
  onExport: (params: { format: "echo" | "janus"; transferVol: number }) => void;
}

type MappingFormat = "echo" | "janus";

const FORMAT_DEFAULTS: Record<
  MappingFormat,
  { transferVol: number; unit: string; min: number; max: number; step: number }
> = {
  echo: { transferVol: 100, unit: "nL", min: 50, max: 5000, step: 1 },
  janus: { transferVol: 2.0, unit: "µL", min: 0.5, max: 10, step: 0.1 },
};

export function MappingExportDialog({
  open,
  initialFormat = "echo",
  onOpenChange,
  onExport,
}: MappingExportDialogProps) {
  const [format, setFormat] = useState<"echo" | "janus">(initialFormat);
  const cfg = FORMAT_DEFAULTS[format];
  const [transferVol, setTransferVol] = useState<number>(cfg.transferVol);

  // Apply initial format when opened; reset transferVol when format changes.
  useEffect(() => {
    if (open) setFormat(initialFormat);
  }, [open, initialFormat]);

  useEffect(() => {
    setTransferVol(FORMAT_DEFAULTS[format].transferVol);
  }, [format]);

  function handleExportClick() {
    onExport({ format, transferVol });
  }

  const label = format === "echo" ? "Echo" : "JANUS";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl">Export {label} Mapping</DialogTitle>
          <DialogDescription className="text-slate-600">
            Two files are written to the same path.
            <br />
            <span className="text-slate-500">.xlsx</span> — human-readable layout preview
            <br />
            <span className="text-slate-500">.csv</span> — machine input (actual liquid-handler upload)
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Machine Format */}
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-4">
            <label className="text-sm font-medium text-slate-700">
              Machine
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={format === "echo" ? "default" : "outline"}
                className={format === "echo" ? "rounded-full" : "rounded-full border-slate-300 bg-white"}
                onClick={() => setFormat("echo")}
                type="button"
              >
                Echo 525
              </Button>
              <Button
                size="sm"
                variant={format === "janus" ? "default" : "outline"}
                className={format === "janus" ? "rounded-full" : "rounded-full border-slate-300 bg-white"}
                onClick={() => setFormat("janus")}
                type="button"
              >
                JANUS
              </Button>
            </div>
          </div>

          {/* Transfer Volume */}
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-4">
            <label className="text-sm font-medium text-slate-700">
              Transfer Volume
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
              <span className="text-sm text-slate-500">{cfg.unit}</span>
            </div>
            <p className="text-xs text-slate-400">
              Range: {cfg.min}–{cfg.max} {cfg.unit}
              {format === "echo" && transferVol > 500 && (
                <span className="ml-2 text-amber-500">
                  ({Math.ceil(transferVol / 500)} transfers × ≤500 nL)
                </span>
              )}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full border-slate-300 bg-white"
            onClick={() => onOpenChange(false)}
            type="button"
          >
            Cancel
          </Button>
          <Button size="sm" className="rounded-full" onClick={handleExportClick} type="button">
            Export
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
