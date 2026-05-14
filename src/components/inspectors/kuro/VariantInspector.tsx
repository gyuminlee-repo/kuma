/**
 * VariantInspector — KURO Design/Nominate screen inspector.
 *
 * Follows selected row in the variant table. When no row is selected, shows
 * a prompt. Data sources:
 *   - inspectedVariant (local prop from parent, tracks table row selection)
 *
 * The store has no global "selected nomination row" state; the parent
 * (DesignStepView or NominatePanel) passes the selected row down.
 * If the parent does not yet supply a row, the inspector shows an empty state.
 *
 * [source: v5-strategy.md §6.1 row 2]
 * [source: mockup v6 line 384]
 */

import { useTranslation } from "react-i18next";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { KvList } from "@/components/inspectors/kuro/shared/KvList";
import { InspectorCallout } from "@/components/inspectors/kuro/shared/InspectorCallout";
import { InspectorEmptyState } from "@/components/inspectors/kuro/shared/InspectorEmptyState";

export type VariantRow = {
  mutation: string;
  activity?: number;
  activityStd?: number;
  reads?: number;
  domain?: string;
  mameLink?: string;
};

type VariantInspectorProps = {
  selected?: VariantRow | null;
};

export function VariantInspector({ selected }: VariantInspectorProps) {
  const { t } = useTranslation();

  return (
    <InspectorPanel title={t("kuro.nominate.inspectorTitle")}>
      {!selected ? (
        <InspectorEmptyState message={t("kuro.inspector.selectRowPrompt")} />
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[13px] font-semibold text-foreground">
              {selected.mutation}
            </span>
            <span className="rounded-sm bg-accent px-1.5 py-0.5 text-[10px] font-medium text-accent-foreground">
              {t("kuro.inspector.selectedBadge")}
            </span>
          </div>
          <KvList
            rows={[
              {
                k: t("kuro.nominate.kvActivity"),
                v:
                  selected.activity != null
                    ? selected.activityStd != null
                      ? `${selected.activity.toFixed(2)} ± ${selected.activityStd.toFixed(2)}`
                      : selected.activity.toFixed(2)
                    : "--",
              },
              {
                k: t("kuro.nominate.kvReads"),
                v:
                  selected.reads != null
                    ? selected.reads.toLocaleString()
                    : "--",
              },
              {
                k: t("kuro.nominate.kvDomain"),
                v: selected.domain ?? "--",
              },
              {
                k: t("kuro.nominate.kvMameLink"),
                v: selected.mameLink ?? "--",
              },
            ]}
          />
        </>
      )}
      <InspectorCallout label={t("kuro.inspector.usefulLabel")}>
        {t("kuro.nominate.calloutText")}
      </InspectorCallout>
    </InspectorPanel>
  );
}
