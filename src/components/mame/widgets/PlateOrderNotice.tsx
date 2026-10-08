/**
 * PlateOrderNotice, "this expected workbook disagrees with its own plate sheet".
 *
 * A KURO export writes the same plate twice: on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When the two disagree and MAME has to take wells from
 * the expected sheet's row order, every well is scored against a variant nobody
 * put there, and the counts and the verdicts still look exactly right. That is
 * why this is stated up front instead of being left in the output to find.
 *
 * Stated and gated. `validate_inputs` reports the disagreement as an error and
 * `selectCanRun` refuses the run while the finding is stored, so this is the
 * explanation next to a Run button that will not press. It was informational
 * between v0.15.6 and 2026-08-05, on the reasoning that a sample map or a
 * confirmed layout made the sheet order irrelevant; those inputs place wells,
 * they do not record which of the workbook's two plates was pipetted, so the
 * run went ahead scored against a plate nobody had checked.
 *
 * No repair is offered, and no override. Which sheet describes the tubes that
 * were actually pipetted is written in no input on this screen, so the way out
 * is a workbook whose sheets agree: re-export from KURO v0.14.3 or later, or
 * pick another file. Picking one clears the finding (`setExpectedPath`) and the
 * re-check writes it back only if the new file disagrees with itself too.
 *
 * Not an error boundary: the file is readable and the inputs are otherwise
 * fine, so this is a blocking notice on the inputs panel, not a crash surface.
 */

import { AlertTriangle } from "lucide-react";
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
      role="alert"
      className="flex items-start gap-2 rounded-control border border-destructive/40 bg-destructive/8 px-2.5 py-1.5"
    >
      <AlertTriangle
        size={12}
        className="mt-0.5 flex-shrink-0 text-destructive"
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-1 text-caption text-destructive">
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
        <p className="break-words">{message.resolution}</p>
      </div>
    </div>
  );
}
