/**
 * WellLabelOptions — label format selection for plate well display.
 *
 * [source: spec §1 — "plate.labels: label format 옵션 (primer name / mutation / variant id)"]
 *
 * v1: local state. Stage 3에서 slice 연결.
 * Note: 컴포넌트 언마운트 시 state 휘발 — Stage 3에서 slice 연결 필요.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export type WellLabelFormat = "primerName" | "mutation" | "variantId";

const FORMATS: { value: WellLabelFormat; labelKey: string }[] = [
  { value: "primerName", labelKey: "phaseC.plate.labelFormat.primerName" },
  { value: "mutation",   labelKey: "phaseC.plate.labelFormat.mutation" },
  { value: "variantId",  labelKey: "phaseC.plate.labelFormat.variantId" },
];

export function WellLabelOptions() {
  const { t } = useTranslation();
  const [labelFormat, setLabelFormat] = useState<WellLabelFormat>("primerName");

  return (
    <div
      className="flex flex-col gap-4 p-6"
      role="region"
      aria-label={t("phaseC.plate.selectLabel")}
    >
      <h3 className="text-sm font-semibold text-foreground">
        {t("phaseC.plate.selectLabel")}
      </h3>
      <div
        role="radiogroup"
        aria-label={t("phaseC.plate.selectLabel")}
        className="flex flex-col gap-3"
      >
        {FORMATS.map((fmt) => (
          <label
            key={fmt.value}
            className={cn(
              "flex items-center gap-2 cursor-pointer text-sm",
              labelFormat === fmt.value ? "text-foreground" : "text-muted-foreground",
            )}
          >
            <input
              type="radio"
              name="well-label-format"
              value={fmt.value}
              checked={labelFormat === fmt.value}
              onChange={() => setLabelFormat(fmt.value)}
              className="accent-primary"
            />
            {t(fmt.labelKey)}
          </label>
        ))}
      </div>
    </div>
  );
}
