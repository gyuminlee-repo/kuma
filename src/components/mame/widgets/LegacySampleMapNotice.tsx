/**
 * LegacySampleMapNotice, the one-time answer to a project that still has a
 * `sample_map_template.xlsx` on disk.
 *
 * The sample map is no longer an input: the plate is computed from the variant
 * list, so there is no second file to keep in step. An existing project still
 * has the old one, though, filled in and checked by hand, and quietly ignoring
 * it is the one option that cannot be defended: if it disagrees with the layout
 * the run would use, one of the two describes the tubes that were pipetted.
 *
 * So `validate_inputs` compares them. A disagreement is named down to the well
 * and lands in `errors`, which is where it is shown. This renders only the other
 * outcome: the two agree, so the run proceeds and the file can go. Dismissible,
 * because it is an announcement rather than a condition, and the next validate
 * would otherwise repeat it for as long as the file exists.
 *
 * The file is never deleted from here. Deleting an operator's record of the
 * bench is not this screen's call.
 */

import { useState } from "react";
import { Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/** Last path segment, for a message that names the file rather than a path. */
function basename(path: string): string {
  const normalised = path.replace(/\\/g, "/");
  return normalised.slice(normalised.lastIndexOf("/") + 1) || path;
}

export function LegacySampleMapNotice() {
  const { t } = useTranslation();
  const finding = useMameAppStore((s) => s.legacySampleMapFinding);
  const [dismissedPath, setDismissedPath] = useState<string | null>(null);

  if (finding === null || finding.status !== "matches") return null;
  if (dismissedPath === finding.path) return null;

  return (
    <div
      role="status"
      data-testid="legacy-sample-map-notice"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/40 px-3 py-2 text-caption"
    >
      <Info size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="font-semibold text-foreground">
          {t("mame.qc.legacySampleMap.title", { file: basename(finding.path) })}
        </p>
        <p className="text-muted-foreground">
          {t("mame.qc.legacySampleMap.desc", { wells: finding.wells_compared })}
        </p>
      </div>
      <button
        type="button"
        className="flex-shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted"
        aria-label={t("mame.qc.legacySampleMap.dismiss")}
        onClick={() => setDismissedPath(finding.path)}
      >
        <X size={14} aria-hidden="true" />
      </button>
    </div>
  );
}
