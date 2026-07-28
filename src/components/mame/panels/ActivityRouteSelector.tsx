/**
 * ActivityRouteSelector, mutually-exclusive picker between the two
 * EVOLVEpro-input generation routes offered by the Activity phase (3.1):
 *
 *   - "genotype": long-format activity upload merged against the current
 *     round's NGS genotype (IngestSection + MergeSection + ExportSection).
 *   - "plateLayout": plate layout + GC data xlsx files, no NGS required
 *     (BuildEvolveproInputPanel).
 *
 * Pure presentational component: state lives in the parent (ActivityStepView)
 * and is persisted there via activityRouteStorage helpers. No store import
 * here, to avoid the store-coupled leaf util → module-eval import cycle this
 * codebase has hit before.
 */

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { ActivityRoute } from "@/lib/mame/activityRouteStorage";

export interface ActivityRouteSelectorProps {
  value: ActivityRoute;
  onChange: (route: ActivityRoute) => void;
}

interface RouteOption {
  value: ActivityRoute;
  labelKey: string;
  descKey: string;
}

const ROUTE_OPTIONS: RouteOption[] = [
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

export function ActivityRouteSelector({ value, onChange }: ActivityRouteSelectorProps) {
  const { t } = useTranslation();

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const currentIndex = ROUTE_OPTIONS.findIndex((opt) => opt.value === value);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + delta + ROUTE_OPTIONS.length) % ROUTE_OPTIONS.length;
    onChange(ROUTE_OPTIONS[nextIndex].value);
  }

  return (
    <section className="space-y-2" aria-label={t("mame.activity.route.heading")}>
      <h3 className="text-sm font-semibold text-foreground">
        {t("mame.activity.route.heading")}
      </h3>
      <div
        role="radiogroup"
        aria-label={t("mame.activity.route.ariaLabel")}
        onKeyDown={handleKeyDown}
        className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      >
        {ROUTE_OPTIONS.map((option) => {
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
