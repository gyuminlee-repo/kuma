/**
 * SourceInspector — KURO Design/Load screen inspector.
 *
 * Data sources:
 *   - evolveproCsvPath  (inputSlice) — loaded CSV file path
 *   - evolveproTotalCount (inputSlice) — total variant count
 *   - evolveproRound (diversitySlice) — round number
 *
 * [source: v5-strategy.md §6.1 row 1]
 * [source: mockup v6 line 367]
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { useShallow } from "zustand/react/shallow";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import { KvList } from "@/components/inspectors/kuro/shared/KvList";
import { InspectorCallout } from "@/components/inspectors/kuro/shared/InspectorCallout";

export function SourceInspector() {
  const { t } = useTranslation();

  const { evolveproCsvPath, evolveproTotalCount, evolveproRound } = useAppStore(
    useShallow((s) => ({
      evolveproCsvPath: s.evolveproCsvPath,
      evolveproTotalCount: s.evolveproTotalCount,
      evolveproRound: s.evolveproRound,
    })),
  );

  const filename = evolveproCsvPath
    ? evolveproCsvPath.split(/[\\/]/).pop() ?? evolveproCsvPath
    : null;

  const rows = [
    {
      k: t("kuro.load.artifactLabel"),
      v: filename ?? t("kuro.inspector.noArtifact"),
    },
    {
      k: t("kuro.inspector.round"),
      v: evolveproRound > 0 ? String(evolveproRound) : "--",
    },
    {
      k: t("kuro.inspector.variants"),
      v: evolveproTotalCount > 0 ? evolveproTotalCount.toLocaleString() : "--",
    },
    {
      k: t("kuro.inspector.format"),
      v: "EVOLVEpro CSV",
    },
  ];

  return (
    <InspectorPanel title={t("kuro.load.inspectorTitle")}>
      {!filename ? (
        <p className="text-[12px] text-muted-foreground">
          {t("kuro.inspector.noArtifact")}
        </p>
      ) : (
        <KvList rows={rows} />
      )}
      <InspectorCallout label={t("kuro.inspector.intentLabel")}>
        {t("kuro.load.intentCallout")}
      </InspectorCallout>
    </InspectorPanel>
  );
}
