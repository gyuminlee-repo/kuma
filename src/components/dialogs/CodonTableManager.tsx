/**
 * Add an organism: import a codon table, or export one to send a colleague.
 *
 * THREE TABS, AND COMPUTE IS THE DEFAULT (design note section 4.2). Phase 3
 * shipped this dialog with Import as the default and a note saying Compute was
 * Phase 4; Phase 4b is that phase. Compute leads because it is the answer for
 * the user this feature was built for -- the one holding a genome and no
 * table. Import and Export are unchanged.
 *
 * WHAT COMPUTE SHOWS BEFORE IT WRITES ANYTHING. How many coding sequences were
 * counted and how many were dropped, with the reason for each drop and a few
 * record identifiers per reason. A preview that says "164 excluded" and names
 * nothing cannot be checked by the person who has the file open. Then the most
 * frequent codon of each amino acid, and the codons furthest from the bundled
 * E. coli table -- the comparison is presentational and rejects nothing; it is
 * there so a user with a feel for E. coli can sanity-check the result.
 *
 * THE GENETIC CODE IS THE USER'S AND IS NOT CORRECTED. Neither a GenBank file
 * nor a CDS FASTA states it in a form worth trusting, so the dialog asks. The
 * value goes to the sidecar as chosen; codes 1 and 11 assign codons
 * identically and differ only in start codons, so a substituted value would
 * pass every check downstream and surface only as two colleagues holding
 * tables that disagree on paper about the same science.
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
  CodonTablePreview,
  ComputeCodonTableParams,
  ComputeCodonTableResult,
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

// The suffixes the sidecar's _ALLOWED_GENOME_EXTENSIONS accepts, split the way
// the file dialog wants them. Kept in step with that set by the
// kuro-custom-codon-tables sync group rather than by a runtime check: the
// browse filter only decides what the picker greys out, and a file that slips
// past it is refused by the sidecar with a sentence of its own.
const GENOME_FILTERS = [
  { name: "GenBank", extensions: ["gbff", "gb", "gbk", "genbank"] },
  { name: "CDS FASTA", extensions: ["fna", "fa", "fasta", "ffn"] },
];

// The exclusion reasons the sidecar reports, in the order it reports them.
// Literal keys rather than `t(`...${reason}`)`: scripts/i18n-parity.mjs
// resolves t() call sites statically and a template key is reported but never
// checked, which is the same reason formatLabel below is a switch.
function exclusionLabel(t: (k: string) => string, reason: string): string {
  switch (reason) {
    case "pseudo":
      return t("codonTable.manager.reasonPseudo");
    case "not_multiple_of_3":
      return t("codonTable.manager.reasonNotMultipleOf3");
    case "internal_stop":
      return t("codonTable.manager.reasonInternalStop");
    case "no_terminal_stop":
      return t("codonTable.manager.reasonNoTerminalStop");
    case "ambiguous_base":
      return t("codonTable.manager.reasonAmbiguousBase");
    default:
      return reason;
  }
}

const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

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

/**
 * What the genome scan counted, rendered as three blocks.
 *
 * It renders; it derives nothing. Every number comes from the sidecar's
 * `preview` block, computed beside the tally that produced it, so there is no
 * second implementation of the same arithmetic sitting where no pytest can
 * reach it. Amino acid letters and codon strings are IUPAC symbols and are not
 * translated.
 */
function ComputePreview({ preview }: { preview: CodonTablePreview }) {
  const { t } = useTranslation();
  const excluded = Object.entries(preview.cds_excluded).filter(([, n]) => n > 0);

  return (
    <div className="space-y-3 rounded-control border border-border p-2">
      <p className="text-xs text-foreground">
        {t("codonTable.manager.previewCounted", {
          counted: preview.cds_counted,
          total: preview.cds_total,
          codons: preview.codon_count,
        })}
      </p>

      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {t("codonTable.manager.excludedLabel")}
        </p>
        {excluded.length === 0 ? (
          <p className="text-xs text-foreground">
            {t("codonTable.manager.excludedNone")}
          </p>
        ) : (
          <ul className="space-y-0.5">
            {excluded.map(([reason, count]) => (
              <li key={reason} className="text-xs text-foreground">
                {exclusionLabel(t, reason)}: {count}
                {/* The identifiers are what make the count checkable against
                    the file the user has open. */}
                {(preview.excluded_examples[reason] ?? []).length > 0 && (
                  <span className="ml-1 font-mono text-muted-foreground">
                    {(preview.excluded_examples[reason] ?? []).join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {t("codonTable.manager.topCodonsLabel")}
        </p>
        <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 font-mono text-xs sm:grid-cols-4">
          {preview.top_codons.map((row) => (
            <span key={row.aa} className="text-foreground">
              {row.aa} {row.codon} {pct(row.fraction)}
            </span>
          ))}
        </div>
      </div>

      {preview.reference_key !== null && preview.divergent_codons.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">
            {t("codonTable.manager.divergentLabel", {
              reference: preview.reference_key,
            })}
          </p>
          <ul className="space-y-0.5 font-mono text-xs">
            {preview.divergent_codons.map((row) => (
              <li key={row.codon} className="text-foreground">
                {row.aa} {row.codon} {pct(row.fraction)} /{" "}
                {pct(row.reference_fraction)}{" "}
                <span className="text-muted-foreground">
                  ({row.delta >= 0 ? "+" : ""}
                  {pct(row.delta)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function CodonTableManager({ open, onOpenChange }: CodonTableManagerProps) {
  const { t } = useTranslation();
  const organisms = useAppStore((s) => s.organisms);
  const previewCodonTable = useAppStore((s) => s.previewCodonTable);
  const importCodonTable = useAppStore((s) => s.importCodonTable);
  const exportCodonTable = useAppStore((s) => s.exportCodonTable);
  const previewComputedCodonTable = useAppStore((s) => s.previewComputedCodonTable);
  const computeCodonTable = useAppStore((s) => s.computeCodonTable);
  // The sidecar reports the scan through the shared progress notification,
  // which lands here. Reading it is the whole of the progress wiring on this
  // side: no new channel, and a scan that takes seconds does not look stalled.
  const statusMessage = useAppStore((s) => s.statusMessage);

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

  // The compute tab keeps its own fields. Sharing key/name/taxid with the
  // import tab would carry a value the user typed for one file onto another,
  // and the key is the identity the table is installed under.
  const [genomePath, setGenomePath] = useState("");
  const [computeKey, setComputeKey] = useState("");
  const [computeName, setComputeName] = useState("");
  const [computeTaxid, setComputeTaxid] = useState("");
  const [computeAliases, setComputeAliases] = useState("");
  const [computeGeneticCode, setComputeGeneticCode] = useState("11");
  const [computeOverwrite, setComputeOverwrite] = useState(false);
  const [computeReport, setComputeReport] =
    useState<ComputeCodonTableResult | null>(null);

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

  const canCompute = computeKey.trim().length > 0 && genomePath.length > 0 && !busy;
  const canInstallComputed = Boolean(computeReport?.ok) && !busy;

  function buildComputeParams(): ComputeCodonTableParams {
    const parsed = computeTaxid.trim() === "" ? null : Number(computeTaxid.trim());
    return {
      filepath: genomePath,
      key: computeKey.trim(),
      name: computeName.trim(),
      taxid: Number.isFinite(parsed as number) ? parsed : null,
      // The user's choice, sent as chosen. No `|| 11` here: the select offers
      // only 1 and 11, so a falsy value cannot arise, and a fallback written
      // anyway is the overwrite this phase exists not to repeat.
      genetic_code: Number(computeGeneticCode),
      aliases: computeAliases
        .split(",")
        .map((a) => a.trim())
        .filter(Boolean),
      overwrite: computeOverwrite,
    };
  }

  async function browseGenome() {
    const { browseFile } = await import("../../lib/file-utils");
    await browseFile(GENOME_FILTERS, (path) => {
      setGenomePath(path);
      setComputeReport(null);
    });
  }

  async function runCompute() {
    setBusy(true);
    setTransportError("");
    try {
      setComputeReport(await previewComputedCodonTable(buildComputeParams()));
    } catch (err) {
      setComputeReport(null);
      setTransportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runComputeInstall() {
    setBusy(true);
    setTransportError("");
    try {
      const result = await computeCodonTable(buildComputeParams());
      setComputeReport(result);
      if (result.installed) onOpenChange(false);
    } catch (err) {
      setTransportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
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

        {/* Compute is the default tab (design note section 4.2): the user this
            dialog was built for is holding a genome, not a table. */}
        <Tabs defaultValue="compute">
          <TabsList>
            <TabsTrigger value="compute">{t("codonTable.manager.computeTab")}</TabsTrigger>
            <TabsTrigger value="import">{t("codonTable.manager.importTab")}</TabsTrigger>
            <TabsTrigger value="export">{t("codonTable.manager.exportTab")}</TabsTrigger>
          </TabsList>

          <TabsContent value="compute" className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {t("codonTable.manager.computeHint")}
            </p>

            <div className="flex items-center gap-2 text-xs">
              <span className="w-28 text-muted-foreground">
                {t("codonTable.manager.genomeLabel")}
              </span>
              <Input
                className="h-8 flex-1 min-w-0 font-mono text-xs"
                value={genomePath}
                readOnly
                placeholder={t("codonTable.manager.genomePlaceholder")}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void browseGenome()}
              >
                {t("codonTable.manager.browse")}
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.keyLabel")}
                </span>
                <Input
                  className="h-8 font-mono text-xs"
                  value={computeKey}
                  onChange={(e) => {
                    setComputeKey(e.target.value);
                    setComputeReport(null);
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
                  value={computeName}
                  onChange={(e) => setComputeName(e.target.value)}
                  placeholder="Methylorubrum extorquens AM1"
                />
              </label>
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.taxidLabel")}
                </span>
                <Input
                  className="h-8 text-xs"
                  value={computeTaxid}
                  onChange={(e) => setComputeTaxid(e.target.value)}
                  placeholder={t("codonTable.manager.taxidPlaceholder")}
                />
              </label>
              {/* Always shown here, unlike on the import tab. A genome file
                  declares no genetic code, so this control is the only source
                  there is and it decides what the stored table says. */}
              <label className="space-y-1">
                <span className="text-muted-foreground">
                  {t("codonTable.manager.geneticCodeLabel")}
                </span>
                <select
                  className="h-8 w-full rounded-control border border-border bg-card px-2 text-xs"
                  value={computeGeneticCode}
                  onChange={(e) => {
                    setComputeGeneticCode(e.target.value);
                    setComputeReport(null);
                  }}
                >
                  <option value="11">{t("codonTable.manager.geneticCode11")}</option>
                  <option value="1">{t("codonTable.manager.geneticCode1")}</option>
                </select>
              </label>
            </div>

            <label className="block space-y-1 text-xs">
              <span className="text-muted-foreground">
                {t("codonTable.manager.aliasesLabel")}
              </span>
              <Input
                className="h-8 text-xs"
                value={computeAliases}
                onChange={(e) => setComputeAliases(e.target.value)}
                placeholder={t("codonTable.manager.aliasesPlaceholder")}
              />
            </label>

            {computeReport?.errors.some((f) => f.code === "V10") && (
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={computeOverwrite}
                  onChange={(e) => {
                    setComputeOverwrite(e.target.checked);
                    setComputeReport(null);
                  }}
                />
                <span>{t("codonTable.manager.overwriteLabel")}</span>
              </label>
            )}

            {/* The scan blocks the sidecar for seconds, and longer on a network
                drive. The sidecar reports each batch of coding sequences
                through the shared progress notification, and echoing the latest
                one here is what keeps the dialog from looking frozen. */}
            {busy && (
              <p className="text-xs text-muted-foreground">
                {statusMessage || t("codonTable.manager.computing")}
              </p>
            )}

            {transportError && (
              <p className="text-xs text-destructive">{transportError}</p>
            )}

            {computeReport && (
              <div className="space-y-2">
                <ComputePreview preview={computeReport.preview} />
                <div className="space-y-2 rounded-control border border-border p-2">
                  <p className="text-xs text-muted-foreground">
                    {t("codonTable.manager.checksRun", {
                      checks: computeReport.checks_performed,
                      codons: computeReport.codons_examined,
                    })}
                  </p>
                  <FindingList
                    findings={computeReport.errors}
                    tone="error"
                    label={t("codonTable.manager.errorsLabel")}
                  />
                  <FindingList
                    findings={computeReport.warnings}
                    tone="warning"
                    label={t("codonTable.manager.warningsLabel")}
                  />
                  <FindingList
                    findings={computeReport.normalizations}
                    tone="info"
                    label={t("codonTable.manager.normalizationsLabel")}
                  />
                  {computeReport.ok && (
                    <p className="text-xs text-foreground">
                      {t("codonTable.manager.readyToInstall", {
                        digest: (computeReport.table_sha256 ?? "").slice(0, 8),
                      })}
                    </p>
                  )}
                </div>
              </div>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={!canCompute}
                onClick={() => void runCompute()}
              >
                {t("codonTable.manager.computeCheck")}
              </Button>
              <Button
                type="button"
                disabled={!canInstallComputed}
                onClick={() => void runComputeInstall()}
              >
                {t("codonTable.manager.computeInstall")}
              </Button>
            </DialogFooter>
          </TabsContent>

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
