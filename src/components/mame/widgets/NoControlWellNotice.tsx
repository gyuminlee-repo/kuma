/**
 * NoControlWellNotice, "this plate carries no WT control well".
 *
 * A run scored without a control well is not a mistake: a Well-column source
 * can name no wild-type row, and a row-order source can ask for none via the
 * WT placement picker (`wt_placement: "none"`). Either way the plate that ran
 * has a different character of evidence than one with a control, and that
 * difference is silent otherwise: `wt_well` reads null exactly the same as
 * every other empty field, and nothing else on this screen says why.
 *
 * Stated, not gated: this does not block the run. The point is to keep the
 * absence visible rather than to second-guess a choice the operator (or the
 * file) already made.
 */

import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/**
 * True when a loaded, non-empty draft carries no control well.
 *
 * `occupants === null` covers "nothing read yet"; `occupants === 0` covers a
 * draft the capacity gate emptied (`dropped_mutant_ids` non-empty), where
 * `wt_well` is also null but for an unrelated reason (nothing was placed at
 * all, not "placed with no control"). Neither warrants this notice.
 */
export function diagnoseNoControlWell(
  wtWell: string | null,
  occupants: number | null,
): boolean {
  return occupants !== null && occupants > 0 && wtWell === null;
}

export function NoControlWellNotice() {
  const { t } = useTranslation();
  const wtWell = useMameAppStore((s) => s.wtWell);
  const occupants = useMameAppStore((s) => s.wellSelectionOccupants);

  if (!diagnoseNoControlWell(wtWell, occupants)) return null;

  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/20 px-2.5 py-1.5 text-caption text-muted-foreground"
    >
      <Info size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <span>{t("mame.wellSelection.noControlWell.body")}</span>
    </p>
  );
}
