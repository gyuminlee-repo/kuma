/**
 * ClonePlateCrosscheckNotice, "these two plates do not name the same clone".
 *
 * There are two plates. KURO orders the primers into a source plate and writes
 * each one's well on `Fwd List`/`Fwd Plate`, assigned by design-sheet index. The
 * run then fills the clone plate by residue position ascending, because that is
 * the order the bench pipettes in. On any export not already written in position
 * order the two name different clones in the same well, and nothing told the
 * operator so.
 *
 * **Stated and not gated**, which is the whole difference from
 * `PlateOrderNotice`. That one explains a Run button that will not press. This
 * one sits beside a Run button that works: the sidecar keeps `valid` true and
 * says nothing in `errors`, and `selectCanRun` does not read this field. A
 * design-ordered export disagrees by construction, and refusing it would refuse
 * nearly every real analyse run.
 *
 * It also offers no repair, because there is nothing here to repair. Which of
 * the two numbers describes the tubes in the rack is not written in any input on
 * this screen; the operator read the labels and the operator is the one who
 * knows. So the copy names the wells and says plainly that the call is theirs.
 *
 * Not dismissible, unlike `LegacySampleMapNotice`. That one announces a file
 * that can go away; this one describes the workbook currently selected, and it
 * disappears on its own when another file is picked (`setExpectedPath`) or when
 * the two plates agree.
 */

import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

export function ClonePlateCrosscheckNotice() {
  const { t } = useTranslation();
  const finding = useMameAppStore((s) => s.clonePlateCrosscheck);

  // Only a mismatch is sent, and only a mismatch is shown. Checking the status
  // rather than the count keeps an unrecognised status from rendering as one.
  if (finding === null || finding.status !== "mismatch") return null;

  return (
    <div
      role="status"
      data-testid="clone-plate-crosscheck-notice"
      className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/10 px-3 py-2 text-caption"
    >
      <Info size={16} className="mt-0.5 flex-shrink-0 text-warning" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-semibold text-foreground break-words">
          {t("mame.qc.clonePlateCrosscheck.title", {
            mismatched: finding.mismatch_count,
            wells: finding.wells_compared,
          })}
        </p>
        <p className="text-muted-foreground break-words">
          {t("mame.qc.clonePlateCrosscheck.desc", {
            sheet: finding.plate_sheet ?? t("mame.qc.clonePlateCrosscheck.unnamedSheet"),
          })}
        </p>
        {finding.examples.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {finding.examples.map((example) => (
              <li key={example.well} className="break-words">
                {t("mame.qc.clonePlateCrosscheck.example", {
                  well: example.well,
                  primer: example.primer_plate || "-",
                  clone: example.clone_plate || "-",
                })}
              </li>
            ))}
          </ul>
        )}
        <p className="text-muted-foreground break-words">
          {t("mame.qc.clonePlateCrosscheck.decision")}
        </p>
      </div>
    </div>
  );
}
