/**
 * KuroPlateView — mame PlateView를 kuro primer status 색상으로 wrapping.
 *
 * plateMappings + designResults로부터 WellEntry 배열을 생성하고
 * wellColorOf callback으로 색상을 주입한다. mame verdict 로직과 완전히 분리.
 *
 * Stage 3: designResults → WellEntry 변환 구현.
 *   - plateMappings 없으면 빈 plate 표시.
 *   - rescue / failed 상태는 SdmPrimerResult.warnings + tolerance_used 기준.
 */

import { useMemo } from "react";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { useAppStore } from "@/store/appStore";
import type { WellColorOverride } from "@/components/mame/widgets/WellPlate";
import type { PlateMapping, SdmPrimerResult } from "@/types/models";
import type { WellEntry } from "@/types/mame/models";

// ---------------------------------------------------------------------------
// Primer status per well
// ---------------------------------------------------------------------------

export type PrimerStatus = "assigned" | "rescued" | "failed" | "empty";

interface KuroWellStatus {
  /** well ID, e.g. "A1" */
  well: string;
  /** mutation tag associated with the primer */
  mutation: string;
  status: PrimerStatus;
}

// ---------------------------------------------------------------------------
// Color map
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<PrimerStatus, WellColorOverride> = {
  empty:    { bg: "#F1F3F5", text: "#C1C8D0", border: "#DDE1E7" },
  assigned: { bg: "#1D4ED8", text: "#FFFFFF", border: "#1E3A8A" }, // primary brand
  rescued:  { bg: "#D97706", text: "#FFFFFF", border: "#92400E" }, // warning
  failed:   { bg: "#DC2626", text: "#FFFFFF", border: "#991B1B" }, // error
};

// ---------------------------------------------------------------------------
// Conversion helpers
// ---------------------------------------------------------------------------

/**
 * Derive PrimerStatus from SdmPrimerResult.
 * - tolerance_used > 0: rescued (design succeeded but with relaxed tolerance)
 * - warnings non-empty: rescued (imperfect but accepted)
 * - otherwise: assigned
 */
function getPrimerStatus(result: SdmPrimerResult | undefined): PrimerStatus {
  if (!result) return "failed";
  if ((result.tolerance_used ?? 0) > 0 || result.warnings.length > 0) return "rescued";
  return "assigned";
}

/**
 * Build a map of mutation → SdmPrimerResult from designResults.
 */
function buildResultMap(
  designResults: SdmPrimerResult[],
): Map<string, SdmPrimerResult> {
  return new Map(designResults.map((r) => [r.mutation, r]));
}

/**
 * Convert PlateMapping array to WellEntry array.
 * mame-specific fields (barcode, verdict) use neutral defaults.
 * wellColorOf callback overrides verdict colors in kuro mode.
 */
function plateMappingsToWellEntries(
  mappings: PlateMapping[],
  wellStatuses: KuroWellStatus[],
): WellEntry[] {
  const statusMap = new Map(wellStatuses.map((s) => [s.well, s.status]));

  return mappings.map((m) => ({
    well: m.well,
    barcode: "kuro",
    native_barcode: "kuro",
    verdict: "PASS" as const, // wellColorOf overrides — verdict ignored in kuro mode
    mutant_id: m.mutation,
    selected: statusMap.get(m.well) === "assigned",
    notes: m.primer_name,
    is_fallback: statusMap.get(m.well) === "rescued",
    fallback_reason: null,
  }));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface KuroPlateViewProps {
  /** Plate mapping data from exportSlice.plateMappings. Empty = blank plate. */
  plateMappings: PlateMapping[];
  /**
   * Per-well primer status override list. When omitted, status is derived
   * from store designResults.
   */
  wellStatuses?: KuroWellStatus[];
  /** 96 | 384 — Stage 1에서는 96만 사용 */
  plateSize?: 96 | 384;
}

export function KuroPlateView({
  plateMappings,
  wellStatuses: externalStatuses,
}: KuroPlateViewProps) {
  const designResults = useAppStore((s) => s.designResults);

  // Derive well statuses from designResults when not provided externally
  const wellStatuses = useMemo<KuroWellStatus[]>(() => {
    if (externalStatuses !== undefined) return externalStatuses;
    if (plateMappings.length === 0) return [];

    const resultMap = buildResultMap(designResults);
    return plateMappings.map((m) => ({
      well: m.well,
      mutation: m.mutation,
      status: getPrimerStatus(resultMap.get(m.mutation)),
    }));
  }, [externalStatuses, plateMappings, designResults]);

  const wellEntries = useMemo(
    () => plateMappingsToWellEntries(plateMappings, wellStatuses),
    [plateMappings, wellStatuses],
  );

  const wellColorOf = useMemo(
    () =>
      (well: WellEntry): WellColorOverride | null => {
        const found = wellStatuses.find((s) => s.well === well.well);
        const status: PrimerStatus = found?.status ?? "empty";
        return STATUS_COLORS[status];
      },
    [wellStatuses],
  );

  // Empty plate: plateMappings is empty → pass empty wells array so no mame store load occurs
  return (
    <PlateView
      wellColorOf={wellColorOf}
      wells={wellEntries}
    />
  );
}
