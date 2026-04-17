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

const FORMAT_DEFAULTS = {
  echo: { transferVol: 100, unit: "nL", min: 50, max: 5000, step: 1 },
  janus: { transferVol: 2.0, unit: "µL", min: 0.5, max: 10, step: 0.1 },
} as const;

export function MappingExportDialog({
  open,
  initialFormat = "echo",
  onOpenChange,
  onExport,
}: MappingExportDialogProps) {
  const [format, setFormat] = useState<"echo" | "janus">(initialFormat);
  const cfg = FORMAT_DEFAULTS[format];
  const [transferVol, setTransferVol] = useState<number>(cfg.transferVol);

  // open될 때 초기 포맷 반영, 포맷 바뀔 때 transferVol 리셋
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
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Export {label} Mapping</DialogTitle>
          <DialogDescription>
            두 파일이 같은 경로에 생성됩니다.
            <br />
            <span className="text-gray-500">.xlsx</span> — 레이아웃 확인용 (사람이 보는 파일)
            <br />
            <span className="text-gray-500">.csv</span> — 기기 업로드용 (실제 머신 인풋)
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Machine Format */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">
              Machine
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={format === "echo" ? "default" : "outline"}
                onClick={() => setFormat("echo")}
                type="button"
              >
                Echo 525
              </Button>
              <Button
                size="sm"
                variant={format === "janus" ? "default" : "outline"}
                onClick={() => setFormat("janus")}
                type="button"
              >
                JANUS
              </Button>
            </div>
          </div>

          {/* Transfer Volume */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-gray-700">
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
              <span className="text-sm text-gray-500">{cfg.unit}</span>
            </div>
            <p className="text-xs text-gray-400">
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
            onClick={() => onOpenChange(false)}
            type="button"
          >
            Cancel
          </Button>
          <Button size="sm" onClick={handleExportClick} type="button">
            Export
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
