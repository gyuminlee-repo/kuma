/**
 * ExportMacrogenSection: standalone Macrogen plate-oligo order form.
 *
 * Lives next to the Export All card on the Export tab. Calls
 * handleExportMacrogen, which invokes the kuro sidecar `export_macrogen` RPC.
 * Purification is fixed to MOPC (see export-handlers.ts:280).
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { save } from "@tauri-apps/plugin-dialog";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { handleExportMacrogen } from "@/components/layout/export-handlers";

const PLATE_NAME_RE = /^[A-Za-z0-9_-]{1,20}$/;

export function ExportMacrogenSection() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string, vars?: Record<string, unknown>) =>
    t(key, { defaultValue: fallback, ...vars });

  const [fwd, setFwd] = useState("");
  const [rev, setRev] = useState("");
  const [amount, setAmount] = useState<"0.05" | "0.2">("0.05");
  const [busy, setBusy] = useState(false);

  const fwdValid = fwd === "" || PLATE_NAME_RE.test(fwd);
  const rvsValid = rev === "" || PLATE_NAME_RE.test(rev);
  const invalid = !fwdValid || !rvsValid;

  async function onExport(): Promise<void> {
    const ts = new Date();
    const yymmdd = ts.toISOString().slice(2, 10).replace(/-/g, "");
    const hhmm = `${String(ts.getHours()).padStart(2, "0")}${String(ts.getMinutes()).padStart(2, "0")}`;
    const defaultPath = `macrogen_${yymmdd}_${hhmm}.xls`;
    try {
      const path = await save({
        defaultPath,
        filters: [{ name: "Macrogen Plate Oligo", extensions: ["xls"] }],
      });
      if (!path) return;
      setBusy(true);
      await handleExportMacrogen({
        outputPath: path,
        fwdPlateName: fwd || undefined,
        rvsPlateName: rev || undefined,
        amount,
      });
      toast.success(
        tx("phaseC.export.macrogen.success", "Macrogen order exported: {{path}}", { path }),
      );
    } catch (e) {
      toast.error(
        tx("phaseC.export.macrogen.error", "Macrogen export failed: {{reason}}", {
          reason: String(e),
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby="export-macrogen-heading"
      className="flex flex-col gap-4 p-6"
    >
      <h3
        id="export-macrogen-heading"
        className="text-sm font-semibold text-foreground"
      >
        {tx("phaseC.export.macrogen.title", "Order Primers (Macrogen)")}
      </h3>

      {/* Forward plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="macrogen-fwd-plate"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.macrogen.fwdPlateName", "Forward plate name")}
        </label>
        <Input
          id="macrogen-fwd-plate"
          value={fwd}
          onChange={(e) => setFwd(e.target.value)}
          placeholder="e.g. FWD_Plate_1"
          className={cn(!fwdValid && "border-destructive")}
        />
        {!fwdValid && (
          <span role="alert" className="text-caption text-destructive">
            {tx(
              "phaseC.export.macrogen.error.plateNameRegex",
              "Use 1-20 letters, numbers, underscores, or hyphens.",
            )}
          </span>
        )}
      </div>

      {/* Reverse plate name */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="macrogen-rev-plate"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.macrogen.revPlateName", "Reverse plate name")}
        </label>
        <Input
          id="macrogen-rev-plate"
          value={rev}
          onChange={(e) => setRev(e.target.value)}
          placeholder="e.g. REV_Plate_1"
          className={cn(!rvsValid && "border-destructive")}
        />
        {!rvsValid && (
          <span role="alert" className="text-caption text-destructive">
            {tx(
              "phaseC.export.macrogen.error.plateNameRegex",
              "Use 1-20 letters, numbers, underscores, or hyphens.",
            )}
          </span>
        )}
      </div>

      {/* Amount */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor="macrogen-amount"
          className="text-sm font-medium text-foreground"
        >
          {tx("phaseC.export.macrogen.amount", "Synthesis amount")}
        </label>
        <div className="flex items-center gap-3">
          <select
            id="macrogen-amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value as "0.05" | "0.2")}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring min-w-0"
          >
            <option value="0.05">0.05 μmole</option>
            <option value="0.2">0.2 μmole</option>
          </select>
          <span className="text-sm text-muted-foreground">
            {tx("phaseC.export.macrogen.purificationFixed", "Purification")}: MOPC
          </span>
        </div>
      </div>

      <Button
        className="w-fit"
        disabled={busy || invalid}
        onClick={() => void onExport()}
      >
        {busy
          ? t("common.loading")
          : tx("phaseC.export.macrogen.orderButton", "Order primers (Macrogen)")}
      </Button>
    </section>
  );
}
