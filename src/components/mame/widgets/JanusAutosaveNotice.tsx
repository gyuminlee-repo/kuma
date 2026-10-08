/**
 * JanusAutosaveNotice, what became of the two Janus files.
 *
 * The two files answer different questions and are written at different
 * times:
 *  - the pick list (`..._picks.csv`, which variant was selected and where it
 *    sits) is written by every finished analyze, unconditionally. Absence has
 *    to be as visible as presence: a run that reports "Analysis complete"
 *    while the file silently failed sends somebody to a folder with nothing
 *    in it.
 *  - the instrument mapping (`..._janus.csv`, the 8-column sheet the robot
 *    reads) is written only when the operator exports one from the step 3
 *    mapping panel. Whatever it derived rather than being told (the plate
 *    names in the two rack columns, generated from the plates of the run)
 *    comes back in `warnings` and is shown here, because a value nobody set is
 *    exactly what the operator has to know before the sheet reaches the robot.
 *
 * Three outcomes, three tones:
 *   "saved"    path and pick count.
 *   "skipped"  nothing was selected, so nothing was written. Not a failure, but
 *              also not a pick list: said plainly. Only the automatic pick
 *              list can reach this state; the mapping export disables its own
 *              button instead of writing an empty file.
 *   "failed"   the reason, verbatim from the sidecar. Only the automatic pick
 *              list writes this status; a failed manual export shows its error
 *              inline on the mapping panel instead of here.
 */

import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { JanusAutosaveResult } from "@/types/mame/models";

function basename(filePath: string): string {
  return filePath.split(/[/\\]/).pop() ?? filePath;
}

/** Which i18n family describes this file, and which testid it carries. */
type NoticeKind = "picks" | "mapping";

export function JanusAutosaveNotice() {
  const picks = useMameAppStore((s) => s.janusAutosave);
  const mapping = useMameAppStore((s) => s.janusMappingAutosave);

  if (!picks && !mapping) return null;

  return (
    <div className="space-y-1.5">
      {picks && <AutosaveLine autosave={picks} kind="picks" />}
      {mapping && <AutosaveLine autosave={mapping} kind="mapping" />}
    </div>
  );
}

function AutosaveLine({
  autosave,
  kind,
}: {
  autosave: JanusAutosaveResult;
  kind: NoticeKind;
}) {
  const { t } = useTranslation();
  const keyBase =
    kind === "picks" ? "mame.analyze.janusAutosave" : "mame.analyze.janusMappingAutosave";
  const testId =
    kind === "picks" ? "janus-autosave-notice" : "janus-mapping-autosave-notice";
  const warnings = autosave.warnings ?? [];

  const failed = autosave.status === "failed";
  const saved = autosave.status === "saved";
  const Icon = failed ? AlertCircle : saved ? CheckCircle2 : Info;
  const tone = failed
    ? "border-error/40 bg-error/8 text-error"
    : saved
      ? "border-success/40 bg-success/8 text-success"
      : "border-border bg-muted/30 text-muted-foreground";

  return (
    <div
      data-testid={testId}
      data-status={autosave.status}
      role={failed ? "alert" : "status"}
      className={`flex items-start gap-2 rounded-control border px-2.5 py-1.5 ${tone}`}
    >
      <Icon size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-1 text-caption">
        <p className="font-medium break-words">
          {t(`${keyBase}.${autosave.status}`, {
            rows: autosave.row_count,
          })}
        </p>
        {saved && autosave.output_path !== null && (
          <p className="break-all font-mono" title={autosave.output_path}>
            {basename(autosave.output_path)}
          </p>
        )}
        {autosave.errors.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4">
            {autosave.errors.map((error) => (
              <li key={error.code} className="break-words">
                {error.message}
              </li>
            ))}
          </ul>
        )}
        {/* What the file left blank or took from the run. Never a failure, so
            it never changes the tone of the line above. */}
        {warnings.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4">
            {warnings.map((warning) => (
              <li key={warning.code} className="break-words">
                {warning.message}
              </li>
            ))}
          </ul>
        )}
        {autosave.excluded_count > 0 && (
          <p className="break-words">
            {/* Not named `count`: that option sends i18next looking for a
                plural variant of the key, and the catalogue carries one form
                in every locale. */}
            {t(`${keyBase}.excluded`, {
              clones: autosave.excluded_count,
            })}
          </p>
        )}
      </div>
    </div>
  );
}
