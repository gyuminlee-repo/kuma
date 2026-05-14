/**
 * InspectorCallout — informational callout block for Inspector panels.
 * Matches mockup `.callout` pattern: border-l-4 accent, bold label + text.
 *
 * [source: mockup v6 inspector callout pattern]
 */

import type { ReactNode } from "react";

type InspectorCalloutProps = {
  label: string;
  children: ReactNode;
};

export function InspectorCallout({ label, children }: InspectorCalloutProps) {
  return (
    <div
      className="mt-3 rounded-md border border-ring/30 bg-accent/20 px-3 py-2 text-[11px] leading-snug text-muted-foreground"
      role="note"
    >
      <span className="font-semibold text-foreground">{label}: </span>
      {children}
    </div>
  );
}
