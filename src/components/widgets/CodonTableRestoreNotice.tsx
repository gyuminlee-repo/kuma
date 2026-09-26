/**
 * The notice that renders one row of the design note's section 8.3 table.
 *
 * It sits under the organism dropdown because that is the control whose value
 * is in question. It is the only place the amino-acid list appears: the Run
 * Design gate (`store/validation.ts`) returns bare i18n keys and cannot carry
 * placeholders, so it refuses the run and this says why.
 *
 * Installing writes the project's copy into the drop-in folder and re-lists.
 * The button is the explicit approval the last row of that table requires; a
 * table that disagrees is never merged and the key is never rewritten.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../store/appStore";
import { resolveCodonTableRestore } from "../../lib/codonTableRestore";
import { Button } from "../ui/button";

export function CodonTableRestoreNotice() {
  const { t } = useTranslation();
  const restoredCodonTable = useAppStore((s) => s.restoredCodonTable);
  const organisms = useAppStore((s) => s.organisms);
  const installRestoredCodonTable = useAppStore((s) => s.installRestoredCodonTable);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);

  const state = resolveCodonTableRestore(restoredCodonTable, organisms);
  if (state.kind === "ok" || state.kind === "pending") return null;

  async function handleInstall() {
    setInstalling(true);
    setInstallError(null);
    try {
      setInstallError(await installRestoredCodonTable());
    } finally {
      setInstalling(false);
    }
  }

  const message =
    state.kind === "installable"
      ? t("codonTable.restore.notInstalled", { name: state.name })
      : state.kind === "absent"
        ? t("codonTable.restore.absent", { key: state.key })
        : state.kind === "mismatchUnexplained"
          ? t("codonTable.restore.mismatchUnexplained", { key: state.key })
          : t("codonTable.restore.mismatch", {
              key: state.key,
              list: state.differingAminoAcids.join(", "),
            });

  const offersInstall =
    state.kind === "installable" || (state.kind === "mismatch" && state.canInstall);

  return (
    <div
      role="status"
      className="mt-1.5 flex flex-col gap-1.5 rounded-control border border-warning/40 bg-warning/10 p-2 text-xs text-foreground"
    >
      <p>{message}</p>
      {offersInstall && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={installing}
            onClick={() => void handleInstall()}
          >
            {installing
              ? t("codonTable.restore.installing")
              : state.kind === "mismatch"
                ? t("codonTable.restore.useProjectCopy")
                : t("codonTable.restore.install")}
          </Button>
          {state.kind === "mismatch" && (
            <span className="text-muted-foreground">
              {t("codonTable.restore.overwriteWarning", { key: state.key })}
            </span>
          )}
        </div>
      )}
      {installError !== null && (
        <p className="text-destructive">
          {t("codonTable.restore.installFailed", { reason: installError })}
        </p>
      )}
    </div>
  );
}
