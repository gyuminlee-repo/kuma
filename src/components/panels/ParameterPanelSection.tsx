/**
 * ParameterPanelSection — wrapper that mounts ParameterPanel for a given section.
 *
 * [source: spec §9 "안전 옵션" — full ParameterPanel mount + scrollIntoView]
 *
 * v1 (Stage 2): section prop is accepted as an interface boundary only.
 * ParameterPanel has no data-section identifiers, so scrollIntoView is deferred.
 * The entire ParameterPanel is mounted for every SDM sub-step to avoid
 * state/effect regressions from partial mounts.
 *
 * TODO Stage 3: add data-section="codon|polymerase|gc-length" identifiers
 *   to ParameterPanel sections, then call:
 *   containerRef.current?.querySelector(`[data-section="${section}"]`)?.scrollIntoView()
 */

import { ParameterPanel } from "@/components/panels/ParameterPanel";

export type ParameterSection = "codon" | "polymerase-tm" | "gc-length";

interface ParameterPanelSectionProps {
  /** Target section to highlight. v1: interface only — full panel always mounted. */
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  section: ParameterSection;
}

export function ParameterPanelSection({ section: _section }: ParameterPanelSectionProps) {
  // TODO Stage 3: scrollIntoView to the section identified by _section prop
  // Requires data-section attributes on ParameterPanel sub-sections.
  return (
    <div className="w-full h-full overflow-y-auto">
      <ParameterPanel />
    </div>
  );
}
