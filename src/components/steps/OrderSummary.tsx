/**
 * OrderSummary — plate count, primer count, mutation count statistics.
 *
 * [source: spec §1 — "export.summary: well 수, 총 primer 수, 비용 추정 (현존 시)"]
 *
 * Data sources:
 *   - totalCount / successCount: designSlice (AppLayout line 73-74)
 *   - plateEstimate: Math.ceil(totalCount / 96) (AppLayout line 179)
 *   - mutationCount: mutationText non-blank non-comment lines
 *
 * Cost estimation: spec §14 미정 (현존 데이터 없음) → v1에서 미표시.
 */

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { getIncludedDesignResults } from "@/store/slices/designSlice.helpers";

export function OrderSummary() {
  const { t } = useTranslation();
  const totalCount = useAppStore((s) => s.totalCount);
  const successCount = useAppStore((s) => s.successCount);
  const mutationText = useAppStore((s) => s.mutationText);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const designResults = useAppStore((s) => s.designResults);
  const excludedDesignMutations = useAppStore((s) => s.excludedDesignMutations);

  const includedSuccessCount =
    mutationInputMode === "evolvepro"
      ? getIncludedDesignResults(designResults, excludedDesignMutations).length
      : successCount;

  const plateEstimate =
    mutationInputMode === "evolvepro"
      ? includedSuccessCount > 0
        ? Math.ceil(includedSuccessCount / 96)
        : null
      : totalCount > 0
        ? Math.ceil(totalCount / 96)
        : null;

  const mutationCount = useMemo(() => {
    if (!mutationText.trim()) return 0;
    return mutationText
      .trim()
      .split("\n")
      .filter((l) => l.trim() && !l.trim().startsWith("#")).length;
  }, [mutationText]);

  const rows = [
    {
      labelKey: "phaseC.export.summary.plateCount",
      value: plateEstimate !== null ? String(plateEstimate) : "—",
    },
    {
      labelKey: "phaseC.export.summary.primerCount",
      value: totalCount > 0 ? `${includedSuccessCount} / ${totalCount}` : "—",
    },
    {
      labelKey: "phaseC.export.summary.mutationCount",
      value: mutationCount > 0 ? String(mutationCount) : "—",
    },
  ];

  return (
    <div
      className="flex flex-col gap-4 p-6"
      role="region"
      aria-label={t("phaseC.subSteps.export.summary")}
    >
      <h3 className="text-sm font-semibold text-foreground">
        {t("phaseC.subSteps.export.summary")}
      </h3>
      <table className="w-full text-sm border-collapse" aria-label={t("phaseC.subSteps.export.summary")}>
        <tbody>
          {rows.map((row) => (
            <tr key={row.labelKey} className="border-b border-border last:border-0">
              <td className="py-2 text-muted-foreground">{t(row.labelKey)}</td>
              <td className="py-2 text-right font-mono text-foreground">{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
