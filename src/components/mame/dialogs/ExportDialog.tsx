import { save } from "@tauri-apps/plugin-dialog";
import { useState, useEffect } from "react";
import { AlertCircle, CheckCircle2, Download, FolderOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
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
import { revealInOSFolder } from "@/lib/openFolder";
import { defaultMameExportFilename } from "@/lib/filename";
import { fileExists, requestOverwriteConfirm } from "@/lib/overwriteConfirm";

function joinPathDialog(dir: string, filename: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir.replace(/[\/]+$/, "")}${sep}${filename}`;
}

export function ExportDialog() {
  const { t } = useTranslation();
  const open = useMameAppStore((s) => s.showExport);
  const closeExport = useMameAppStore((s) => s.closeExport);
  const outputPath = useMameAppStore((s) => s.outputPath); // folder
  const inputDir = useMameAppStore((s) => s.inputDir);
  const referencePath = useMameAppStore((s) => s.referencePath);
  const verdictCount = useMameAppStore((s) => s.verdicts.length);
  const exportExcel = useMameAppStore((s) => s.exportExcel);
  const isExporting = useMameAppStore((s) => s.isExporting);
  const exportError = useMameAppStore((s) => s.exportError);
  const lastExportPath = useMameAppStore((s) => s.lastExportPath);
  const lastExportAt = useMameAppStore((s) => s.lastExportAt);

  // Local full path state: seeded from outputPath(folder)+defaultFilename or lastExportPath.
  const [fullPath, setFullPath] = useState<string>(() => {
    if (lastExportPath) return lastExportPath;
    if (outputPath) return joinPathDialog(outputPath, defaultMameExportFilename({ referencePath, inputDir, verdictCount }));
    return "";
  });

  // Re-seed when dialog opens or outputPath folder changes.
  useEffect(() => {
    if (!open) return;
    if (lastExportPath) {
      setFullPath(lastExportPath);
    } else if (outputPath) {
      setFullPath(joinPathDialog(outputPath, defaultMameExportFilename({ referencePath, inputDir, verdictCount })));
    }
  }, [open, outputPath, lastExportPath, referencePath, inputDir, verdictCount]);

  async function browseOutput() {
    const selected = await save({ filters: [{ name: "Excel", extensions: ["xlsx"] }] });
    if (selected) setFullPath(selected);
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && closeExport()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("mame.dialogs.export.title")}</DialogTitle>
          <DialogDescription>
            {t("mame.dialogs.export.descriptionBase")}{" "}
            <span className="font-medium text-foreground">
              {t("mame.dialogs.export.descriptionSheets")}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="export-output-path" className="text-xs font-medium text-muted-foreground">
              {t("mame.dialogs.export.outputPathLabel")}
            </Label>
            <div className="flex gap-2">
              <Input
                id="export-output-path"
                value={fullPath}
                onChange={(e) => setFullPath(e.target.value)}
                placeholder={t("mame.dialogs.export.outputPathPlaceholder")}
                className="h-9 flex-1 text-sm font-mono"
                aria-label={t("mame.dialogs.export.outputPathAriaLabel")}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseOutput()}
                className="h-9 gap-1.5 px-3 flex-shrink-0"
                aria-label={t("mame.dialogs.export.browseAriaLabel")}
              >
                <FolderOpen size={14} aria-hidden="true" />
                {t("common.browse")}
              </Button>
            </div>
          </div>

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

          {(lastExportPath || lastExportAt) && (
            <div className="rounded-control border border-success/40 bg-success/8 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={13} className="text-success" aria-hidden="true" />
                  <span className="text-caption font-medium text-success">
                    {t("mame.dialogs.export.lastExport")}
                  </span>
                </div>
                {lastExportPath && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 gap-1 px-2 text-caption text-muted-foreground hover:text-foreground"
                    onClick={() => void revealInOSFolder(lastExportPath)}
                    aria-label={t("mame.dialogs.export.openFolderAriaLabel")}
                  >
                    <FolderOpen size={12} aria-hidden="true" />
                    {t("common.openFolder")}
                  </Button>
                )}
              </div>
              {lastExportPath && (
                <p className="mt-1 text-caption font-mono text-foreground break-all">{lastExportPath}</p>
              )}
              {lastExportAt && <p className="text-caption text-muted-foreground">{lastExportAt}</p>}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={closeExport} disabled={isExporting}>
            {t("common.close")}
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              if (!fullPath) return;
              // §5 덮어쓰기 confirm
              if (await fileExists(fullPath)) {
                const decision = await requestOverwriteConfirm(fullPath);
                if (decision === "cancel") return;
              }
              await exportExcel(fullPath);
            }}
            disabled={isExporting || !fullPath}
            className="gap-2"
          >
            <Download size={14} aria-hidden="true" />
            {isExporting ? t("mame.dialogs.export.exporting") : t("mame.dialogs.export.exportExcel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
