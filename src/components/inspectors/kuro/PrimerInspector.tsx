/**
 * PrimerInspector — KURO Output/Summary screen inspector.
 *
 * Follows selected primer row. When no row is selected, shows a prompt.
 * Parent (OutputStepView / ResultTable) passes the selected result down.
 *
 * Data sources (via prop):
 *   - selected: SdmPrimerResult | null
 *   - plateMapping: PlateMapping[] (to derive well position)
 *
 * [source: v5-strategy.md §6.1 row 5]
 * [source: mockup v6 line 428]
 */

import { useTranslation } from "react-i18next";
import type { SdmPrimerResult, PlateMapping } from "@/types/models";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { KvList } from "@/components/inspectors/kuro/shared/KvList";
import { InspectorEmptyState } from "@/components/inspectors/kuro/shared/InspectorEmptyState";

type PrimerInspectorProps = {
  selected?: SdmPrimerResult | null;
  plateMappings?: PlateMapping[];
};

function truncateSeq(seq: string, maxLen = 8): string {
  if (seq.length <= maxLen) return seq;
  return `${seq.slice(0, 4)}...${seq.slice(-4)}`;
}

export function PrimerInspector({ selected, plateMappings = [] }: PrimerInspectorProps) {
  const { t } = useTranslation();

  if (!selected) {
    return (
      <InspectorPanel title={t("kuro.output.inspectorTitle")}>
        <InspectorEmptyState message={t("kuro.inspector.selectRowPrompt")} />
      </InspectorPanel>
    );
  }

  // Find well assignments from plate mappings for this mutation
  const fwdWell = plateMappings.find(
    (m) => m.mutation === selected.mutation && m.primer_type === "forward",
  );
  const revWell = plateMappings.find(
    (m) => m.mutation === selected.mutation && m.primer_type === "reverse",
  );
  const wellValue =
    fwdWell && revWell
      ? `${fwdWell.well} / ${revWell.well}`
      : fwdWell?.well ?? revWell?.well ?? "--";

  const statusValue =
    selected.warnings.length > 0
      ? `WARN (${selected.warnings.length})`
      : "PASS";

  return (
    <InspectorPanel title={t("kuro.output.inspectorTitle")}>
      <div className="mb-2">
        <span className="text-[13px] font-semibold text-foreground">
          {selected.mutation}
        </span>
      </div>
      <KvList
        rows={[
          {
            k: t("kuro.output.kvFwd"),
            v: truncateSeq(selected.forward_seq),
          },
          {
            k: t("kuro.output.kvRev"),
            v: truncateSeq(selected.reverse_seq),
          },
          {
            k: "Plate",
            v: wellValue,
          },
          {
            k: t("kuro.output.kvStatus"),
            v: statusValue,
          },
        ]}
        mono
      />
    </InspectorPanel>
  );
}
