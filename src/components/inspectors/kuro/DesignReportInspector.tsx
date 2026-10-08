/**
 * DesignReportInspector — inline mount of DesignReportContent in the Output
 * inspector slot. Renders empty state when no design has run yet
 * (designResults.length === 0).
 *
 * [source: B4 removes showReport dialog; C2 spec — empty-state via designResults]
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { DesignReportContent } from "@/components/dialogs/DesignReportContent";
import { InspectorEmptyState } from "./shared/InspectorEmptyState";

export function DesignReportInspector() {
  const { t } = useTranslation();
  const hasResults = useAppStore((s) => s.designResults.length > 0);

  if (!hasResults) {
    return <InspectorEmptyState message={t("kuro.inspector.report.empty")} />;
  }

  return <DesignReportContent />;
}
