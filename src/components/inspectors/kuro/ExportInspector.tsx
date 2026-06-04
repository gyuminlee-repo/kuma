/**
 * ExportInspector — KURO Export/All screen inspector.
 *
 * Shows MAME handoff information for the current export.
 * Data sources:
 *   - designResults (designSlice) — variant count
 *   - plateMappings (exportSlice) — plate count
 *   - evolveproCsvPath (inputSlice) — source artifact staleness indicator
 *
 * [source: v5-strategy.md §6.1 row 6]
 * [source: mockup v6 line 445]
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { useShallow } from "zustand/react/shallow";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { KvList } from "@/components/inspectors/kuro/shared/KvList";
import { InspectorCallout } from "@/components/inspectors/kuro/shared/InspectorCallout";
import { InspectorEmptyState } from "@/components/inspectors/kuro/shared/InspectorEmptyState";
import { getIncludedDesignResults } from "@/store/slices/designSlice.helpers";

export function ExportInspector() {
  const { t } = useTranslation();

  const { designResults, excludedDesignMutations, plateMappings, evolveproCsvPath } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      excludedDesignMutations: s.excludedDesignMutations,
      plateMappings: s.plateMappings,
      evolveproCsvPath: s.evolveproCsvPath,
    })),
  );

  if (designResults.length === 0) {
    return (
      <InspectorPanel title={t("kuro.export.inspectorTitle")}>
        <InspectorEmptyState message={t("kuro.inspector.noDesignResults")} />
        <InspectorCallout label={t("kuro.inspector.implementationLabel")}>
          {t("kuro.export.handoffCallout")}
        </InspectorCallout>
      </InspectorPanel>
    );
  }

  const variantCount = getIncludedDesignResults(
    designResults,
    excludedDesignMutations,
  ).length;
  const plateCount =
    plateMappings.length > 0 ? Math.ceil(plateMappings.length / 96) : 1;
  const staleValue = evolveproCsvPath ? t("kuro.inspector.stalenessLinked") : "--";

  return (
    <InspectorPanel title={t("kuro.export.inspectorTitle")}>
      <div className="mb-2 min-w-0">
        <span className="inline-flex items-center gap-1.5 rounded-sm bg-accent px-1.5 py-0.5 text-[10px] font-medium text-accent-foreground">
          {t("kuro.inspector.bridgeBadge")}
        </span>
      </div>
      <KvList
        rows={[
          {
            k: t("kuro.export.kvDestination"),
            v: t("kuro.inspector.exportTargets"),
          },
          {
            k: t("kuro.inspector.variants"),
            v: variantCount.toLocaleString(),
          },
          {
            k: t("kuro.inspector.plateMap"),
            v: t("kuro.inspector.nPlates", { count: plateCount }),
          },
          {
            k: t("kuro.export.kvStaleness"),
            v: staleValue,
          },
        ]}
      />
      <InspectorCallout label={t("kuro.inspector.implementationLabel")}>
        {t("kuro.export.handoffCallout")}
      </InspectorCallout>
    </InspectorPanel>
  );
}
