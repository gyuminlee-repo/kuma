/**
 * RunReportDialog — Export a 1-page HTML/PDF run report (A14 spec).
 *
 * Provides:
 *  - HTML / PDF format selection (radio group)
 *  - Output path with Browse button
 *  - Export button that calls sidecar `export_run_report` RPC
 *  - PDF-unavailable notice when weasyprint is absent
 *  - Success / error feedback inline
 *
 * Entered via: File > Export Run Report… in MenuBar.
 */

import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { AlertCircle, CheckCircle2, Download, FolderOpen, Info } from "lucide-react";
import { useKumaProject } from "@/state/projectContext";
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
import { buildRunReportDefaultPath, handleExportRunReport } from "@/lib/mame/runReport";
import type { RunReportFormat, RunReportResult } from "@/types/mame/models";

interface RunReportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RunReportDialog({ open, onOpenChange }: RunReportDialogProps) {
  const project = useKumaProject();

  const storeIsExporting = useMameAppStore((s) => s.isExporting);
  const [format, setFormat] = useState<RunReportFormat>("html");
  const [outputPath, setOutputPath] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<RunReportResult | null>(null);

  function deriveDefaultPath(fmt: RunReportFormat): string {
    if (!project) return "";
    return buildRunReportDefaultPath(project.path, project.name, fmt);
  }

  function handleFormatChange(next: RunReportFormat) {
    setFormat(next);
    // Update path extension when format toggles if path matches the auto-generated default.
    if (outputPath === "" || outputPath === deriveDefaultPath(format)) {
      setOutputPath(deriveDefaultPath(next));
    }
  }

  async function browseOutput() {
    const ext = format;
    const selected = await save({
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
      defaultPath: outputPath || deriveDefaultPath(format) || undefined,
    });
    if (selected) setOutputPath(selected);
  }

  async function doExport() {
    const target = outputPath || deriveDefaultPath(format);
    if (!target) {
      setExportError("Output path is required.");
      return;
    }
    setIsExporting(true);
    setExportError(null);
    setLastResult(null);
    try {
      const result = await handleExportRunReport(target, format, project?.name);
      setLastResult(result);
      setOutputPath(result.output_path);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsExporting(false);
    }
  }

  const resolvedPath = outputPath || deriveDefaultPath(format);
  const pdfNote = format === "pdf";

  return (
    <Dialog open={open} onOpenChange={(next) => !isExporting && onOpenChange(next)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Export Run Report</DialogTitle>
          <DialogDescription>
            Generate a 1-page summary report combining run metadata, verdict
            statistics, plate breakdown, and file-size distribution.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Format selection */}
          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">Format</legend>
            <div className="flex gap-4" role="radiogroup" aria-label="Report format">
              {(["html", "pdf"] as const).map((fmt) => (
                <label
                  key={fmt}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="report-format"
                    value={fmt}
                    checked={format === fmt}
                    onChange={() => handleFormatChange(fmt)}
                    className="accent-primary"
                    aria-label={fmt.toUpperCase()}
                  />
                  <span className="font-medium uppercase">{fmt}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {/* PDF notice */}
          {pdfNote && (
            <div
              className="flex items-start gap-2 rounded-control border border-primary/30 bg-primary/5 px-3 py-2"
              role="note"
            >
              <Info size={14} className="mt-0.5 flex-shrink-0 text-primary" aria-hidden="true" />
              <p className="text-caption text-muted-foreground">
                PDF export requires{" "}
                <code className="font-mono text-xs">weasyprint</code> to be
                installed. If unavailable, an HTML file is saved instead and
                the result will indicate the fallback.
              </p>
            </div>
          )}

          {/* Output path */}
          <div className="space-y-1.5">
            <Label
              htmlFor="report-output-path"
              className="text-xs font-medium text-muted-foreground"
            >
              Output file path
            </Label>
            <div className="flex gap-2">
              <Input
                id="report-output-path"
                value={resolvedPath}
                onChange={(e) => setOutputPath(e.target.value)}
                placeholder={`Target .${format} file path`}
                className="h-9 flex-1 min-w-0 text-sm font-mono"
                aria-label="Output file path"
                disabled={isExporting}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseOutput()}
                className="h-9 gap-1.5 px-3 flex-shrink-0"
                aria-label="Browse save path"
                disabled={isExporting}
              >
                <FolderOpen size={14} aria-hidden="true" />
                Browse
              </Button>
            </div>
          </div>

          {/* Fallback notice after export */}
          {lastResult?.fallback_to_html && !exportError && (
            <div
              className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/8 px-3 py-2"
              role="status"
              aria-live="polite"
            >
              <Info size={14} className="mt-0.5 flex-shrink-0 text-warning" aria-hidden="true" />
              <p className="text-caption text-warning">
                weasyprint was not found — report saved as HTML instead.
              </p>
            </div>
          )}

          {/* Error */}
          {exportError && (
            <div
              className="flex items-start gap-2 rounded-control border border-error/40 bg-error/8 px-3 py-2"
              role="alert"
              aria-live="assertive"
            >
              <AlertCircle size={14} className="mt-0.5 flex-shrink-0 text-error" aria-hidden="true" />
              <p className="text-caption text-error">{exportError}</p>
            </div>
          )}

          {/* Success */}
          {lastResult && !exportError && !lastResult.fallback_to_html && (
            <div className="rounded-control border border-success/40 bg-success/8 px-3 py-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} className="text-success" aria-hidden="true" />
                <span className="text-caption font-medium text-success">
                  Exported as {lastResult.format.toUpperCase()}
                </span>
              </div>
              <p className="mt-1 text-caption font-mono text-foreground break-all">
                {lastResult.output_path}
              </p>
            </div>
          )}

          {/* Success with fallback indicator */}
          {lastResult?.fallback_to_html && !exportError && (
            <div className="rounded-control border border-warning/40 bg-warning/5 px-3 py-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} className="text-success" aria-hidden="true" />
                <span className="text-caption font-medium text-foreground">Saved (HTML fallback)</span>
              </div>
              <p className="mt-1 text-caption font-mono text-foreground break-all">
                {lastResult.output_path}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isExporting}
          >
            Close
          </Button>
          <Button
            size="sm"
            onClick={() => void doExport()}
            disabled={isExporting || storeIsExporting || !resolvedPath}
            className="gap-2"
          >
            <Download size={14} aria-hidden="true" />
            {isExporting ? "Exporting…" : "Export Report"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
