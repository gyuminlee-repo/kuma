import { save } from "@tauri-apps/plugin-dialog";
import { AlertCircle, CheckCircle2, Download, FolderOpen } from "lucide-react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ExportDialog() {
  const open = useMameAppStore((s) => s.showExport);
  const closeExport = useMameAppStore((s) => s.closeExport);
  const outputPath = useMameAppStore((s) => s.outputPath);
  const setOutputPath = useMameAppStore((s) => s.setOutputPath);
  const exportExcel = useMameAppStore((s) => s.exportExcel);
  const isExporting = useMameAppStore((s) => s.isExporting);
  const exportError = useMameAppStore((s) => s.exportError);
  const lastExportPath = useMameAppStore((s) => s.lastExportPath);
  const lastExportAt = useMameAppStore((s) => s.lastExportAt);

  async function browseOutput() {
    const selected = await save({ filters: [{ name: "Excel", extensions: ["xlsx"] }] });
    if (selected) setOutputPath(selected);
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && closeExport()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Export Results</DialogTitle>
          <DialogDescription>Save the complete verdict set as an Excel workbook.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="export-output-path" className="text-xs font-medium text-muted-foreground">
              Output file path
            </Label>
            <div className="flex gap-2">
              <Input
                id="export-output-path"
                value={outputPath}
                onChange={(e) => setOutputPath(e.target.value)}
                placeholder="Target .xlsx file path"
                className="h-9 flex-1 text-sm font-mono"
                aria-label="Output file path"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseOutput()}
                className="h-9 gap-1.5 px-3 flex-shrink-0"
                aria-label="Browse save path"
              >
                <FolderOpen size={14} aria-hidden="true" />
                Browse
              </Button>
            </div>
          </div>

          {exportError && (
            <div
              className="flex items-start gap-2 rounded-md border border-[hsl(var(--verdict-fail))] bg-[hsl(var(--verdict-fail)/0.08)] px-3 py-2"
              role="alert"
              aria-live="assertive"
            >
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0 text-[hsl(var(--verdict-fail))]" aria-hidden="true" />
              <p className="text-xs text-[hsl(var(--verdict-fail))]">{exportError}</p>
            </div>
          )}

          {(lastExportPath || lastExportAt) && (
            <div className="rounded-md border border-[hsl(var(--verdict-pass)/0.4)] bg-[hsl(var(--verdict-pass)/0.08)] px-3 py-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} className="text-[hsl(var(--verdict-pass))]" aria-hidden="true" />
                <span className="text-xs font-medium text-[hsl(var(--verdict-pass))]">Last export</span>
              </div>
              {lastExportPath && (
                <p className="mt-1 text-[11px] font-mono text-foreground break-all">{lastExportPath}</p>
              )}
              {lastExportAt && <p className="text-[11px] text-muted-foreground">{lastExportAt}</p>}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={closeExport} disabled={isExporting}>
            Close
          </Button>
          <Button
            size="sm"
            onClick={() => void exportExcel(outputPath)}
            disabled={isExporting || !outputPath}
            className="gap-2"
          >
            <Download size={14} aria-hidden="true" />
            {isExporting ? "Exporting…" : "Export Excel"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
