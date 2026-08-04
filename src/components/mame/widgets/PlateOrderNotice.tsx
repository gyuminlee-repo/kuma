/**
 * PlateOrderNotice, "this expected workbook disagrees with its own plate sheet".
 *
 * A KURO export writes the same plate twice: on `Fwd List`/`Fwd Plate` and on
 * `expected_mutations`. When the two disagree and MAME has to take wells from
 * the expected sheet's row order, every well is scored against a variant nobody
 * put there, and the counts and the verdicts still look exactly right. That is
 * why this is stated up front instead of being left in the output to find.
 *
 * Two tones, off the graded severity:
 *   "blocking"  the layout is inferred from the expected sheet, so the sheet
 *               order is the well coordinate system. The run is stopped
 *               (selectCanRun) and the notice says how to proceed.
 *   "info"      a sample map or a confirmed well layout supplies the wells, so
 *               this run is unaffected. Stated, not gated.
 *
 * No repair is offered. Which sheet describes the tubes that were actually
 * pipetted is the operator's call, so the way past a blocking finding is to
 * state the well mapping (sample map, or Build well layout and confirm it), not
 * to have this component pick a sheet.
 *
 * Not an error boundary: the file is readable and the inputs are otherwise
 * fine, so this is a notice on the inputs panel, not a crash surface.
 */

import { AlertTriangle, Info } from "lucide-react";
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
  const blocking = severity === "blocking";
  const Icon = blocking ? AlertTriangle : Info;

  return (
    <div
      data-testid="plate-order-notice"
      data-severity={severity}
      role={blocking ? "alert" : "status"}
      className={
        blocking
          ? "flex items-start gap-2 rounded-control border border-error/40 bg-error/8 px-2.5 py-1.5"
          : "flex items-start gap-2 rounded-control border border-warning/40 bg-warning/8 px-2.5 py-1.5"
      }
    >
      <Icon
        size={12}
        className={
          blocking
            ? "mt-0.5 flex-shrink-0 text-error"
            : "mt-0.5 flex-shrink-0 text-warning"
        }
        aria-hidden="true"
      />
      <div
        className={
          blocking
            ? "min-w-0 space-y-1 text-caption text-error"
            : "min-w-0 space-y-1 text-caption text-warning"
        }
      >
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
        {message.escape !== null && <p className="break-words">{message.escape}</p>}
      </div>
    </div>
  );
}
