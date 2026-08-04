/**
 * ActivitySourceSelector, "where do this round's activity values come from".
 *
 * v0.15.6 folded the two EVOLVEpro-input routes into one step. There is no
 * route to choose any more: sequencing happens in every campaign this workflow
 * describes, so the NGS verdicts are always part of the answer and the only
 * open question is which file carries the measured activity.
 *
 * The two answers, both carried over from the routes they replace:
 *   - "genotype":    a long-format activity upload, joined to the round's NGS
 *                    genotype (IngestSection + MergeSection + ExportSection).
 *   - "plateLayout": a plate layout with GC data or a raw Agilent report, whose
 *                    per-well handling (WT-block normalisation, round-1
 *                    baseline selection, v0.13.27) lives in
 *                    BuildEvolveproInputPanel and is gated there by the NGS
 *                    verdict file.
 *
 * The stored values keep the old names so a saved selection survives the
 * rename (see activityRouteStorage.ts).
 *
 * Pure presentational component: state lives in the parent (ActivityStepView)
 * and is persisted there via activityRouteStorage helpers. No store import
 * here, to avoid the store-coupled leaf util → module-eval import cycle this
 * codebase has hit before.
 */

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { ActivityRoute } from "@/lib/mame/activityRouteStorage";

export interface ActivitySourceSelectorProps {
  value: ActivityRoute;
  onChange: (route: ActivityRoute) => void;
}

interface SourceOption {
  value: ActivityRoute;
  labelKey: string;
  descKey: string;
}

const SOURCE_OPTIONS: SourceOption[] = [
  {
    value: "genotype",
    labelKey: "mame.activity.route.genotypeLabel",
    descKey: "mame.activity.route.genotypeDesc",
  },
  {
    value: "plateLayout",
    labelKey: "mame.activity.route.plateLayoutLabel",
    descKey: "mame.activity.route.plateLayoutDesc",
  },
];

export function ActivitySourceSelector({ value, onChange }: ActivitySourceSelectorProps) {
  const { t } = useTranslation();

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const currentIndex = SOURCE_OPTIONS.findIndex((opt) => opt.value === value);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + delta + SOURCE_OPTIONS.length) % SOURCE_OPTIONS.length;
    onChange(SOURCE_OPTIONS[nextIndex].value);
  }

  return (
    <section className="space-y-2" aria-label={t("mame.activity.route.heading")}>
      <h3 className="text-sm font-semibold text-foreground">
        {t("mame.activity.route.heading")}
      </h3>
      <p className="text-xs text-muted-foreground">
        {t("mame.activity.route.ngsNote")}
      </p>
      <div
        role="radiogroup"
        aria-label={t("mame.activity.route.ariaLabel")}
        onKeyDown={handleKeyDown}
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      >
        {SOURCE_OPTIONS.map((option) => {
          const checked = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={checked}
              tabIndex={checked ? 0 : -1}
              onClick={() => onChange(option.value)}
              className={cn(
                "min-w-0 rounded-md border px-3 py-2 text-left text-xs transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                checked
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/40",
              )}
            >
              <span className="block font-semibold text-foreground">
                {t(option.labelKey)}
              </span>
              <span className="mt-0.5 block text-muted-foreground">
                {t(option.descKey)}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
