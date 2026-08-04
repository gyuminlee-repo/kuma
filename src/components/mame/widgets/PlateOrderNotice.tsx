/**
 * PlateOrderNotice, "this expected workbook disagrees with its own plate sheet".
 *
 * A KURO export writes the same plate twice: on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When the two disagree and MAME has to take wells from
 * the expected sheet's row order, every well is scored against a variant nobody
 * put there, and the counts and the verdicts still look exactly right. That is
 * why this is stated up front instead of being left in the output to find.
 *
 * Stated, never gated. Since v0.15.6 the operator names the sheet and the
 * column the variant list is read from, so the program has no standing to
 * refuse the run over a disagreement between two sheets of one workbook; and
 * once they have named them, this says nothing at all (selectPlateOrderSeverity
 * returns null). What it never stops saying is `missing_from_expected`: a
 * mutant on the plate with no row in the list shifts every later well by one,
 * which happens even when the sheet order is respected and is invisible in the
 * output.
 *
 * No repair is offered. Which sheet describes the tubes that were actually
 * pipetted is the operator's call, so the way to take the sheet order out of a
 * run is to name the sheet and column, or to state the wells with a sample map,
 * not to have this component pick a sheet.
 *
 * Not an error boundary: the file is readable and the inputs are otherwise
 * fine, so this is a notice on the inputs panel, not a crash surface.
 */

import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { buildPlateOrderMessage } from "@/lib/mame/plateOrderMessage";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { selectPlateOrderSeverity } from "@/store/mame/selectors";

export function PlateOrderNotice() {
  // Subscribed so a language switch re-renders the copy; the message itself is
  // built from i18next so the two stay on the same catalogue.
  useTranslation();
  const finding = useMameAppStore((s) => s.plateOrderFinding);
  const severity = useMameAppStore(selectPlateOrderSeverity);
  const expectedPath = useMameAppStore((s) => s.expectedPath);

  if (!finding || severity === null) return null;

  const message = buildPlateOrderMessage({ ...finding, severity }, expectedPath);

  return (
    <div
      data-testid="plate-order-notice"
      data-severity={severity}
      role="status"
      className="flex items-start gap-2 rounded-control border border-warning/40 bg-warning/8 px-2.5 py-1.5"
    >
      <Info
        size={12}
        className="mt-0.5 flex-shrink-0 text-warning"
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-1 text-caption text-warning">
        <p className="font-medium break-words">{message.title}</p>
        <p className="break-words">{message.body}</p>
        {message.examples.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4">
            {message.examples.map((example) => (
              <li key={example} className="break-words">
                {example}
              </li>
            ))}
          </ul>
        )}
        {message.missing !== null && <p className="break-words">{message.missing}</p>}
        <p className="break-words">{message.escape}</p>
      </div>
    </div>
  );
}
