import { useState } from "react";
import { PLATE_PREVIEW_LABEL } from "@/lib/platePreviewStyles";

export function usePreviewPlate(names: readonly string[]) {
  const plates = [...new Set(names)];
  const [selection, setSelection] = useState(plates[0] ?? "");
  const selected = plates.includes(selection) ? selection : (plates[0] ?? "");
  // Reconcile a removed plate immediately, so it cannot reappear as a stale selection.
  if (selected !== selection) setSelection(selected);
  return { plates, selected, setSelection };
}

export function PlatePreviewSelector({ title, plates, selected, onChange }: {
  readonly title: string;
  readonly plates: readonly string[];
  readonly selected: string;
  readonly onChange: (plate: string) => void;
}) {
  return (
    <label className={`${PLATE_PREVIEW_LABEL} flex flex-wrap items-center gap-2`}>
      <span>{title}</span>
      {plates.length > 1 ? (
        <select
          aria-label={title}
          value={selected}
          onChange={(event) => onChange(event.target.value)}
          className="min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {plates.map((plate) => <option key={plate} value={plate}>{plate}</option>)}
        </select>
      ) : selected ? <span>{selected}</span> : null}
    </label>
  );
}
