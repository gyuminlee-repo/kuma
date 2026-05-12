/**
 * PlateSizeSelector — 96/384 plate size toggle.
 *
 * [source: spec §1 — "plate.size: 96/384 toggle (신규, mame PlateView props로 전달)"]
 *
 * v1: local state. Stage 3에서 navigationSlice 또는 별도 plateSlice로 연결.
 * Note: 컴포넌트 언마운트 시 state 휘발 — Stage 3에서 slice 연결 필요.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export type PlateSize = 96 | 384;

export function PlateSizeSelector() {
  const { t } = useTranslation();
  const [plateSize, setPlateSize] = useState<PlateSize>(96);

  const options: { value: PlateSize; labelKey: string }[] = [
    { value: 96, labelKey: "phaseC.plate.size96" },
    { value: 384, labelKey: "phaseC.plate.size384" },
  ];

  return (
    <div
      className="flex flex-col gap-4 p-6"
      role="region"
      aria-label={t("phaseC.plate.selectSize")}
    >
      <h3 className="text-sm font-semibold text-foreground">
        {t("phaseC.plate.selectSize")}
      </h3>
      <div
        role="radiogroup"
        aria-label={t("phaseC.plate.selectSize")}
        className="flex gap-6"
      >
        {options.map((opt) => (
          <label
            key={opt.value}
            className={cn(
              "flex items-center gap-2 cursor-pointer text-sm",
              plateSize === opt.value ? "text-foreground" : "text-muted-foreground",
            )}
          >
            <input
              type="radio"
              name="plate-size"
              value={String(opt.value)}
              checked={plateSize === opt.value}
              onChange={() => setPlateSize(opt.value)}
              className="accent-primary"
            />
            {t(opt.labelKey)}
          </label>
        ))}
      </div>
    </div>
  );
}
