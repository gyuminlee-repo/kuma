/**
 * StaleUnitsNotice, "this folder also held plates from an earlier run".
 *
 * A demux output folder is stable so a re-run can resume, and nothing removes
 * what an earlier run left in it. Export a new run into a folder that already
 * holds one, and both sets of unit directories sit there side by side, each
 * internally valid and each carrying its own completion marker. Every per-unit
 * check passes and the folder as a whole is still wrong.
 *
 * On 2026-08-10 a run declaring three native barcodes was scored over six
 * plates for exactly that reason, and four verdict workbooks were produced
 * before anyone noticed. Nothing on screen said the extra three plates came
 * from the day before, which is what let it repeat.
 *
 * The leftovers are now excluded from the verdicts by the run manifest the
 * producing run writes into the folder, and this states which directories were
 * left out and which run owns them. It stops there: the files are untouched on
 * disk, because deleting a previous run output is the operator's decision and
 * a wrong guess here destroys the only copy.
 */

import { FolderClock } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { StaleUnits } from "@/types/mame/models";

/**
 * The leftover directory names worth showing, or null when there is nothing to
 * say.
 *
 * Null covers two different silences that must not be collapsed. A null
 * `staleUnits` means the folder carried no run manifest, so membership was
 * never recorded and nothing was checked: that is the externally sorted
 * directory a user points MAME at directly, where every subdirectory is meant
 * to be read. An empty `names` means the folder WAS checked and holds nothing
 * stale. Neither warrants a notice, and neither is evidence for the other.
 */
export function diagnoseStaleUnits(staleUnits: StaleUnits | null): string[] | null {
  if (staleUnits === null) return null;
  const names = staleUnits.names.filter((name) => name.length > 0);
  return names.length > 0 ? names : null;
}

export function StaleUnitsNotice() {
  const { t } = useTranslation();
  const staleUnits = useMameAppStore((s) => s.staleUnits);
  const titleId = useId();

  const names = diagnoseStaleUnits(staleUnits);
  if (names === null || staleUnits === null) return null;

  return (
    <section
      aria-labelledby={titleId}
      className="rounded-control border border-warning/40 bg-warning/10 p-3"
    >
      <div className="flex items-start gap-2">
        <FolderClock
          className="mt-0.5 h-4 w-4 shrink-0 text-warning"
          aria-hidden
        />
        <div className="min-w-0 space-y-1">
          <h3 id={titleId} className="text-caption font-medium">
            {/* Passed as `n`, not `count`: `count` is the i18next plural
                selector and would demand a full set of plural suffixes in ten
                locales for a number that only ever reads as a quantity here. */}
            {t("mame.analyze.staleUnits.title", { n: names.length })}
          </h3>
          <p className="text-caption text-muted-foreground">
            {t("mame.analyze.staleUnits.body", { names: names.join(", ") })}
          </p>
          {staleUnits.run_dir.length > 0 && (
            <p className="text-caption text-muted-foreground">
              {t("mame.analyze.staleUnits.owner", {
                runDir: staleUnits.run_dir,
              })}
            </p>
          )}
          <p className="text-caption text-muted-foreground">
            {t("mame.analyze.staleUnits.hint")}
          </p>
        </div>
      </div>
    </section>
  );
}
