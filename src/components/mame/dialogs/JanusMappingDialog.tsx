/**
 * JanusMappingDialog — Export final cell-stock Janus mapping (K4 spec).
 *
 * Provides:
 *  - CSV / XLSX format selection (radio group)
 *  - Output path with Browse button
 *  - Export button that calls sidecar `export_janus_mapping` RPC
 *  - Success / error feedback inline
 *
 * Entered via: File > Export Janus Mapping… in MenuBar.
 */

import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { AlertCircle, CheckCircle2, Download, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
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
import { JanusDeckPreview } from "@/components/mame/widgets/JanusDeckPreview";
import { buildJanusDefaultPath, handleExportMameJanusMapping } from "@/lib/mame/janus";
import type { JanusExportFormat } from "@/types/mame/models";

interface JanusMappingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function JanusMappingDialog({ open, onOpenChange }: JanusMappingDialogProps) {
  const { t } = useTranslation();
  const project = useKumaProject();

  const storeIsExporting = useMameAppStore((s) => s.isExporting);
  const [format, setFormat] = useState<JanusExportFormat>("csv");
  const [outputPath, setOutputPath] = useState<string>("");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [lastExportPath, setLastExportPath] = useState<string | null>(null);

  function deriveDefaultPath(fmt: JanusExportFormat): string {
    if (!project) return "";
    return buildJanusDefaultPath(project.path, project.name, fmt);
  }

  function handleFormatChange(next: JanusExportFormat) {
    setFormat(next);
    // Update path extension when format toggles if path is still the auto-generated default.
    if (outputPath === "" || outputPath === deriveDefaultPath(format)) {
      setOutputPath(deriveDefaultPath(next));
    }
  }

  async function browseOutput() {
    const ext = format === "xlsx" ? "xlsx" : "csv";
    const selected = await save({
      filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
      defaultPath: outputPath || deriveDefaultPath(format) || undefined,
    });
    if (selected) setOutputPath(selected);
  }

  async function doExport() {
    const target = outputPath || deriveDefaultPath(format);
    if (!target) {
      setExportError(t("mame.dialogs.janusMapping.exportErrorPathRequired"));
      return;
    }
    setIsExporting(true);
    setExportError(null);
    try {
      const result = await handleExportMameJanusMapping(target, format);
      setLastExportPath(result.output_path);
      setOutputPath(result.output_path);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsExporting(false);
    }
  }

  const resolvedPath = outputPath || deriveDefaultPath(format);

  return (
    <Dialog open={open} onOpenChange={(next) => !isExporting && onOpenChange(next)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("mame.dialogs.janusMapping.title")}</DialogTitle>
          <DialogDescription>
            {t("mame.dialogs.janusMapping.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Deck preview (PI hmk4 slide 5) */}
          <JanusDeckPreview />

          {/* Format selection */}
          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">
              {t("mame.dialogs.janusMapping.formatLabel")}
            </legend>
            <div className="flex gap-4" role="radiogroup" aria-label={t("mame.dialogs.janusMapping.formatAriaLabel")}>
              {(["csv", "xlsx"] as const).map((fmt) => (
                <label
                  key={fmt}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="radio"
                    name="janus-format"
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

          {/* Output path */}
          <div className="space-y-1.5">
            <Label
              htmlFor="janus-output-path"
              className="text-xs font-medium text-muted-foreground"
            >
              {t("mame.dialogs.janusMapping.outputPathLabel")}
            </Label>
            <div className="flex gap-2">
              <Input
                id="janus-output-path"
                value={resolvedPath}
                onChange={(e) => setOutputPath(e.target.value)}
                placeholder={t("mame.dialogs.janusMapping.outputPathPlaceholder", { ext: format })}
                className="h-9 flex-1 min-w-0 text-sm font-mono"
                aria-label={t("mame.dialogs.janusMapping.outputPathAriaLabel")}
                disabled={isExporting}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseOutput()}
                className="h-9 gap-1.5 px-3 flex-shrink-0"
                aria-label={t("mame.dialogs.janusMapping.browseAriaLabel")}
                disabled={isExporting}
              >
                <FolderOpen size={14} aria-hidden="true" />
              </Button>
            </div>
          </div>

          {/* Column info note */}
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t("mame.dialogs.janusMapping.columnsNote")}
            <br />
            <span className="text-warning">
              {t("mame.dialogs.janusMapping.phase1Note")}
            </span>
          </p>

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
          {lastExportPath && !exportError && (
            <div className="rounded-control border border-success/40 bg-success/8 px-3 py-2">
              <div className="flex items-center gap-2">
                <CheckCircle2 size={13} className="text-success" aria-hidden="true" />
                <span className="text-caption font-medium text-success">
                  {t("mame.dialogs.janusMapping.exported")}
                </span>
              </div>
              <p className="mt-1 text-caption font-mono text-foreground break-all">
                {lastExportPath}
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
            {t("common.close")}
          </Button>
          <Button
            size="sm"
            onClick={() => void doExport()}
            disabled={isExporting || storeIsExporting || !resolvedPath}
            className="gap-2"
          >
            <Download size={14} aria-hidden="true" />
            {isExporting ? t("mame.dialogs.janusMapping.exporting") : t("mame.dialogs.janusMapping.exportJanus")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
