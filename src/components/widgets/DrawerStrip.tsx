import { type ReactNode } from "react";

export type DrawerSlot = {
  title: string;
  children: ReactNode;
};

export type DrawerStripProps = {
  left?: DrawerSlot;
  /** Typically log output */
  center?: DrawerSlot;
  right?: DrawerSlot;
};

/**
 * DrawerStrip: bottom drawer with 3 fixed-width slots.
 * Min height 92px (mockup CSS line 180-185); auto-grows when a slot needs
 * more than 92px (e.g. MAME review summary with 3 stat lines) so the last
 * line is never clipped. Grid: 260px / 1fr / 250px.
 */
export function DrawerStrip({ left, center, right }: DrawerStripProps) {
  return (
    <div
      className="shrink-0 border-t border-border bg-card"
      style={{
        minHeight: "92px",
        display: "grid",
        gridTemplateColumns: "minmax(180px, 260px) minmax(0, 1fr) minmax(180px, 250px)",
      }}
      role="region"
      aria-label="action-drawer"
    >
      <SlotCell slot={left} border />
      <SlotCell slot={center} border />
      <SlotCell slot={right} />
    </div>
  );
}

function SlotCell({ slot, border }: { slot?: DrawerSlot; border?: boolean }) {
  return (
    <div
      className={[
        "flex min-w-0 flex-col overflow-hidden gap-1 px-3 py-[9px]",
        border ? "border-r border-border" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {slot && (
        <>
          <h4 className="mb-1.5 shrink-0 truncate text-[12px] font-semibold text-foreground">
            {slot.title}
          </h4>
          <div className="min-h-0 flex-1 overflow-hidden text-[11px]">
            {slot.children}
          </div>
        </>
      )}
    </div>
  );
}
