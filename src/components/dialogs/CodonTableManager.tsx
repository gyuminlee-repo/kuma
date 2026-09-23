/**
 * Add an organism: import a codon table, or export one to send a colleague.
 *
 * TWO TABS, NOT THREE. The design note's Phase 3 listed "Compute from a
 * genome" as the default tab. That is Phase 4 and it is not here; Import is
 * the default because it is the only one that works today.
 *
 * NO LOOKUP TAB, AND THAT IS A DECISION RATHER THAN AN OMISSION. Searching a
 * public database by taxid is the path where a user learns after five clicks
 * that their strain is not in it -- and a non-model strain is the reason they
 * opened this dialog. In a lab behind an institutional proxy that re-signs
 * TLS, the sidecar's certifi bundle does not trust the re-signed chain and the
 * lookup fails outright (design note section 4.2).
 *
 * PREVIEW BEFORE INSTALL. "Check file" runs the import with `dry_run`, so what
 * it reports is what the install would report, from one call with one flag
 * flipped. Errors, warnings and normalizations render through
 * `formatCodonTableMessage`, the same function the organism listing uses, so a
 * rule reads the same wherever the user meets it.
 *
 * NORMALIZATIONS ARE SHOWN HERE ON PURPOSE. N1 (U converted to T), N2 (codons
 * uppercased) and N4 (frequencies recomputed from counts) say what the import
 * silently changed. This is the one moment the user can still decide not to
 * install the table, which is what makes them worth a panel rather than a log
 * line.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { formatCodonTableMessage } from "../../lib/codonTableMessages";
import { useAppStore } from "../../store/appStore";
import type {
  CodonTableImportFinding,
  ImportCodonTableParams,
  ImportCodonTableResult,
} from "../../types/models";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

type ImportFormat = ImportCodonTableParams["format"];
type ExportFormat = "json" | "csv" | "cusp";

const IMPORT_FORMATS: ImportFormat[] = ["json", "csv", "cusp", "kazusa"];
const EXPORT_FORMATS: ExportFormat[] = ["json", "csv", "cusp"];

// The suffix each import format is browsed for. Kazusa is a page saved from a
// browser, so it has no suffix of its own; the format is always chosen in the
// dialog and never inferred from the file name.
const BROWSE_FILTERS: Record<ImportFormat, { name: string; extensions: string[] }> = {
  json: { name: "kuma codon table", extensions: ["json"] },
  csv: { name: "CSV", extensions: ["csv"] },
  cusp: { name: "EMBOSS cusp", extensions: ["cusp", "cut"] },
  kazusa: { name: "Text", extensions: ["txt"] },
};

// A real row from a Kazusa page, shown as the paste placeholder. Not a locale
// key: a line of codon data reads the same in every language, so translating
// it means nine locales carrying a value identical to English forever.
const KAZUSA_SAMPLE = "UUU F 0.58 22.4 ( 10345)  UUC F 0.42 16.0 (  7412)";

const EXPORT_SUFFIX: Record<ExportFormat, string> = {
  json: "json",
  csv: "csv",
  cusp: "cusp",
};

/**
 * Format name -> locale key, as literal calls.
 *
 * Not `t(`codonTable.manager.format.${f}`)`. scripts/i18n-parity.mjs resolves
 * t() call sites statically and a template key lands in `dynamicKeyCalls`,
 * reported but never checked; codonTableMessages.ts carries the same note and
 * the same shape for the same reason.
 */
function formatLabel(t: (k: string) => string, fmt: ImportFormat): string {
  switch (fmt) {
    case "json":
      return t("codonTable.manager.formatJson");
    case "csv":
      return t("codonTable.manager.formatCsv");
    case "cusp":
      return t("codonTable.manager.formatCusp");
    case "kazusa":
      return t("codonTable.manager.formatKazusa");
  }
}

interface CodonTableManagerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function FindingList({
  findings,
  tone,
  label,
}: {
  findings: CodonTableImportFinding[];
  tone: "error" | "warning" | "info";
  label: string;
}) {
  const { t } = useTranslation();
  if (findings.length === 0) return null;
  const color =
    tone === "error"
      ? "text-destructive"
      : tone === "warning"
        ? "text-amber-600 dark:text-amber-400"
        : "text-muted-foreground";
  return (
    <div className="space-y-1">
      <p className={`text-xs font-medium ${color}`}>{label}</p>
      <ul className="space-y-1">
        {findings.map((f, i) => (
          <li key={`${f.code}-${i}`} className="text-xs text-foreground">
            <span className="font-mono text-muted-foreground">{f.code}</span>{" "}
            {/* Always the localized sentence. formatCodonTableMessage falls
                back to a sentence naming the code for one it does not know, so
                the backend's English `detail` is never rendered: a code with no
                translation still reads as a message rather than a blank line. */}
            {formatCodonTableMessage(t, f.code, f.params)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CodonTableManager({ open, onOpenChange }: CodonTableManagerProps) {
  const { t } = useTranslation();
  const organisms = useAppStore((s) => s.organisms);
  const previewCodonTable = useAppStore((s) => s.previewCodonTable);
  const importCodonTable = useAppStore((s) => s.importCodonTable);
  const exportCodonTable = useAppStore((s) => s.exportCodonTable);

  const [format, setFormat] = useState<ImportFormat>("json");
  const [filepath, setFilepath] = useState("");
  const [pasted, setPasted] = useState("");
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [taxid, setTaxid] = useState("");
  const [aliases, setAliases] = useState("");
  const [geneticCode, setGeneticCode] = useState("11");
  const [overwrite, setOverwrite] = useState(false);
  const [report, setReport] = useState<ImportCodonTableResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [transportError, setTransportError] = useState("");

  const [exportKey, setExportKey] = useState("");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("json");

  const usesPaste = format === "kazusa";
  const hasSource = usesPaste ? pasted.trim().length > 0 : filepath.length > 0;
  const canCheck = key.trim().length > 0 && hasSource && !busy;
  // A preview that passed is the only thing that enables Import. The user has
  // then seen every warning and normalization the install will apply.
  const canImport = Boolean(report?.ok) && !busy;

  function buildParams(): ImportCodonTableParams {
    const parsedTaxid = taxid.trim() === "" ? null : Number(taxid.trim());
    return {
      format,
      key: key.trim(),
      filepath: usesPaste ? undefined : filepath,
      text: usesPaste ? pasted : undefined,
      name: name.trim(),
      taxid: Number.isFinite(parsedTaxid as number) ? parsedTaxid : null,
      genetic_code: Number(geneticCode) || 11,
      aliases: aliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean),
      overwrite,
    };
  }

  async function browse() {
    const { browseFile } = await import("../../lib/file-utils");
    await browseFile([BROWSE_FILTERS[format]], (path) => {
      setFilepath(path);
      setReport(null);
    });
  }

  async function runCheck() {
    setBusy(true);
    setTransportError("");
    try {
      setReport(await previewCodonTable(buildParams()));
    } catch (err) {
      setReport(null);
      setTransportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    setBusy(true);
    setTransportError("");
    try {
      const result = await importCodonTable(buildParams());
      setReport(result);
      if (result.installed) onOpenChange(false);
    } catch (err) {
      setTransportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runExport() {
    if (!exportKey) return;
    const { save } = await import("@tauri-apps/plugin-dialog");
    const path = await save({
      filters: [
        { name: exportFormat, extensions: [EXPORT_SUFFIX[exportFormat]] },
      ],
      defaultPath: `${exportKey}.${EXPORT_SUFFIX[exportFormat]}`,
    });
    if (!path) return;
    setBusy(true);
    setTransportError("");
    try {
      await exportCodonTable({ key: exportKey, format: exportFormat, filepath: path });
      onOpenChange(false);
    } catch (err) {
      setTransportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("codonTable.manager.title")}</DialogTitle>
          <DialogDescription>{t("codonTable.manager.description")}</DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="import">
          <TabsList>
            <TabsTrigger value="import">{t("codonTable.manager.importTab")}</TabsTrigger>
            <TabsTrigger value="export">{t("codonTable.manager.exportTab")}</TabsTrigger>
          </TabsList>

          <TabsContent value="import" className="space-y-3">
            <label className="flex items-center gap-2 text-xs">
              <span className="w-28 text-muted-foreground">
                {t("codonTable.manager.formatLabel")}
              </span>
              <select
                className="h-8 flex-1 min-w-0 rounded-control border border-border bg-card px-2 text-xs"
                value={format}
                onChange={(e) => {
                  setFormat(e.target.value as ImportFormat);
                  setReport(null);
                }}
              >
                {IMPORT_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {formatLabel(t, f)}
                  </option>
                ))}
              </select>
            </label>

            {usesPaste ? (
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.pasteLabel")}
                </span>
                <textarea
                  className="h-28 w-full rounded-control border border-border bg-card p-2 font-mono text-xs"
                  value={pasted}
                  onChange={(e) => {
                    setPasted(e.target.value);
                    setReport(null);
                  }}
                  placeholder={KAZUSA_SAMPLE}
                />
              </label>
            ) : (
              <div className="flex items-center gap-2 text-xs">
                <span className="w-28 text-muted-foreground">
                  {t("codonTable.manager.fileLabel")}
                </span>
                <Input
                  className="h-8 flex-1 min-w-0 font-mono text-xs"
                  value={filepath}
                  readOnly
                  placeholder={t("codonTable.manager.filePlaceholder")}
                />
                <Button type="button" variant="outline" size="sm" onClick={() => void browse()}>
                  {t("codonTable.manager.browse")}
                </Button>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 text-xs">
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.keyLabel")}
                </span>
                <Input
                  className="h-8 font-mono text-xs"
                  value={key}
                  onChange={(e) => {
                    setKey(e.target.value);
                    setReport(null);
                  }}
                  placeholder="mextorquens_lab"
                />
              </label>
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.nameLabel")}
                </span>
                <Input
                  className="h-8 text-xs"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Methylorubrum extorquens AM1"
                />
              </label>
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.taxidLabel")}
                </span>
                <Input
                  className="h-8 text-xs"
                  value={taxid}
                  onChange={(e) => setTaxid(e.target.value)}
                  placeholder={t("codonTable.manager.taxidPlaceholder")}
                />
              </label>
              {/* Hidden for kuma JSON, where the file's own genetic_code is
                  authoritative and the handler ignores this field. The code is
                  an input to the canonical digest, so letting the dialog
                  override a colleague's declared value would give their table
                  a different digest here than on the machine that made it. A
                  control that cannot change the outcome should not be on
                  screen claiming it can. */}
              {format !== "json" && (
                <label className="space-y-1">
                  <span className="text-muted-foreground">
                    {t("codonTable.manager.geneticCodeLabel")}
                  </span>
                  <select
                    className="h-8 w-full rounded-control border border-border bg-card px-2 text-xs"
                    value={geneticCode}
                    onChange={(e) => {
                      setGeneticCode(e.target.value);
                      setReport(null);
                    }}
                  >
                    <option value="11">{t("codonTable.manager.geneticCode11")}</option>
                    <option value="1">{t("codonTable.manager.geneticCode1")}</option>
                  </select>
                </label>
              )}
            </div>

            <label className="block space-y-1 text-xs">
              <span className="text-muted-foreground">
                {t("codonTable.manager.aliasesLabel")}
              </span>
              <Input
                className="h-8 text-xs"
                value={aliases}
                onChange={(e) => setAliases(e.target.value)}
                placeholder={t("codonTable.manager.aliasesPlaceholder")}
              />
            </label>

            {/* Shown only once V10 has actually fired. An overwrite checkbox
                offered before there is anything to overwrite invites the user
                to arm a replacement they do not need. */}
            {report?.errors.some((f) => f.code === "V10") && (
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={overwrite}
                  onChange={(e) => {
                    setOverwrite(e.target.checked);
                    setReport(null);
                  }}
                />
                <span>{t("codonTable.manager.overwriteLabel")}</span>
              </label>
            )}

            {transportError && (
              <p className="text-xs text-destructive">{transportError}</p>
            )}

            {report && (
              <div className="space-y-2 rounded-control border border-border p-2">
                {/* The count is the point: "no problems found" after zero
                    checks and after two hundred must not read the same. */}
                <p className="text-xs text-muted-foreground">
                  {t("codonTable.manager.checksRun", {
                    checks: report.checks_performed,
                    codons: report.codons_examined,
                  })}
                </p>
                <FindingList
                  findings={report.errors}
                  tone="error"
                  label={t("codonTable.manager.errorsLabel")}
                />
                <FindingList
                  findings={report.warnings}
                  tone="warning"
                  label={t("codonTable.manager.warningsLabel")}
                />
                <FindingList
                  findings={report.normalizations}
                  tone="info"
                  label={t("codonTable.manager.normalizationsLabel")}
                />
                {report.ok && (
                  <p className="text-xs text-foreground">
                    {t("codonTable.manager.readyToInstall", {
                      digest: (report.table_sha256 ?? "").slice(0, 8),
                    })}
                  </p>
                )}
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" disabled={!canCheck} onClick={() => void runCheck()}>
                {t("codonTable.manager.check")}
              </Button>
              <Button type="button" disabled={!canImport} onClick={() => void runImport()}>
                {t("codonTable.manager.import")}
              </Button>
            </DialogFooter>
          </TabsContent>

          <TabsContent value="export" className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {t("codonTable.manager.exportHint")}
            </p>
            <label className="flex items-center gap-2 text-xs">
              <span className="w-28 text-muted-foreground">
                {t("codonTable.manager.tableLabel")}
              </span>
              <select
                className="h-8 flex-1 min-w-0 rounded-control border border-border bg-card px-2 text-xs"
                value={exportKey}
                onChange={(e) => setExportKey(e.target.value)}
              >
                <option value="">{t("codonTable.manager.choose")}</option>
                {organisms.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs">
              <span className="w-28 text-muted-foreground">
                {t("codonTable.manager.formatLabel")}
              </span>
              <select
                className="h-8 flex-1 min-w-0 rounded-control border border-border bg-card px-2 text-xs"
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
              >
                {EXPORT_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {formatLabel(t, f)}
                  </option>
                ))}
              </select>
            </label>
            {transportError && (
              <p className="text-xs text-destructive">{transportError}</p>
            )}
            <DialogFooter>
              <Button
                type="button"
                disabled={!exportKey || busy}
                onClick={() => void runExport()}
              >
                {t("codonTable.manager.export")}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
