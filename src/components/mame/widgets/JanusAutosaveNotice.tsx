/**
 * JanusAutosaveNotice, what became of the pick list the run wrote itself.
 *
 * Every finished analyze writes its picks next to the result workbook: which
 * variant was selected, on which plate and well it sits, and where it should be
 * collected. That file is the conclusion of the run, so its absence has to be as
 * visible as its presence: a run that reports "Analysis complete" while the file
 * silently failed sends somebody to a folder that has no file in it.
 *
 * The text must not read as a robot worklist. That file carries deck and liquid
 * parameters, is made in the Janus dialog once the deck is confirmed, and the
 * copy here points there rather than at the File menu, whose Janus item was
 * removed in v0.14.7.
 *
 * Three outcomes, three tones:
 *   "saved"    path and pick count.
 *   "skipped"  nothing was selected, so nothing was written. Not a failure, but
 *              also not a pick list: said plainly.
 *   "failed"   the reason, verbatim from the sidecar.
 */

import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

function basename(filePath: string): string {
  return filePath.split(/[/\\]/).pop() ?? filePath;
}

export function JanusAutosaveNotice() {
  const { t } = useTranslation();
  const autosave = useMameAppStore((s) => s.janusAutosave);

  if (!autosave) return null;

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
      data-testid="janus-autosave-notice"
      data-status={autosave.status}
      role={failed ? "alert" : "status"}
      className={`flex items-start gap-2 rounded-control border px-2.5 py-1.5 ${tone}`}
    >
      <Icon size={12} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-1 text-caption">
        <p className="font-medium break-words">
          {t(`mame.analyze.janusAutosave.${autosave.status}`, {
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
        {autosave.excluded_count > 0 && (
          <p className="break-words">
            {/* Not named `count`: that option sends i18next looking for a
                plural variant of the key, and the catalogue carries one form
                in every locale. */}
            {t("mame.analyze.janusAutosave.excluded", {
              clones: autosave.excluded_count,
            })}
          </p>
        )}
      </div>
    </div>
  );
}
