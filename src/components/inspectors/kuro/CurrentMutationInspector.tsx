/**
 * CurrentMutationInspector — KURO Design/Submit screen inspector.
 *
 * Shows in-progress design details. Default open per v5-strategy (the
 * "collapsed demo" in the mockup is MOCKUP ONLY).
 *
 * Data sources:
 *   - isDesigning (designSlice) — whether design job is running
 *   - statusMessage (designSlice / store) — last progress text from sidecar
 *   - successCount / totalCount (designSlice) — partial completion ratio
 *
 * [source: v5-strategy.md §6.1 row 4, §10 "Inspector collapsed demo = MOCKUP ONLY"]
 * [source: mockup v6 line 415]
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { useShallow } from "zustand/react/shallow";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { KvList } from "@/components/inspectors/kuro/shared/KvList";
import { InspectorCallout } from "@/components/inspectors/kuro/shared/InspectorCallout";

export function CurrentMutationInspector() {
  const { t } = useTranslation();

  const { isDesigning, statusMessage, successCount, totalCount } = useAppStore(
    useShallow((s) => ({
      isDesigning: s.isDesigning,
      statusMessage: s.statusMessage,
      successCount: s.successCount,
      totalCount: s.totalCount,
    })),
  );

  const progressValue =
    totalCount > 0
      ? `${successCount} / ${totalCount}`
      : isDesigning
        ? t("kuro.inspector.running")
        : "--";

  const partialSaveValue = isDesigning
    ? t("kuro.inspector.partialSavePending")
    : successCount > 0
      ? t("kuro.inspector.partialSaveReady")
      : "--";

  return (
    <InspectorPanel title={t("kuro.submit.inspectorTitle")}>
      <KvList
        rows={[
          {
            k: t("kuro.submit.kvMutation"),
            v: statusMessage ?? "--",
          },
          {
            k: t("kuro.submit.kvProgress"),
            v: progressValue,
          },
          {
            k: t("kuro.submit.kvPartialSave"),
            v: partialSaveValue,
          },
        ]}
      />
      <InspectorCallout label={t("kuro.inspector.dataContractLabel")}>
        {t("kuro.submit.contractCallout")}
      </InspectorCallout>
    </InspectorPanel>
  );
}
