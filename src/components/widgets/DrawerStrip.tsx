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
 * DrawerStrip — 92px bottom drawer with 3 fixed-width slots.
 * Grid: 260px / 1fr / 250px. Matches mockup CSS line 180-185.
 */
export function DrawerStrip({ left, center, right }: DrawerStripProps) {
  return (
    <div
      className="shrink-0 border-t border-border bg-card"
      style={{
        height: "92px",
        display: "grid",
        gridTemplateColumns: "260px 1fr 250px",
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
        "flex min-w-0 flex-col overflow-hidden px-3 py-[9px]",
        border ? "border-r border-border" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {slot && (
        <>
          <h4 className="mb-1.5 shrink-0 text-[12px] font-semibold text-foreground">
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
