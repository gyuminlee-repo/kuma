/**
 * JanusDeckPreview — static visualization of the JANUS deck layout
 *
 * Shows the standard 4×2 deck slot positions with conventional labels
 * (tip flush, source plates P1/P2/P3, waste, final 96 deep well).
 * Mirrors PI Project3_개요_hmk4.pptx slide 5.
 *
 * Per PI note "deck이 아니라 plate name설정하고 소프트웨어에서 매칭",
 * the JANUS software matches by plate name, so the deck slot positions
 * shown here are conventional only — no interactive mapping is needed
 * at this stage.
 */

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

type SlotKind = "source" | "destination" | "tip" | "waste" | "blank";

interface DeckSlot {
  id: string;
  kind: SlotKind;
  labelKey: string;
}

const DECK_LAYOUT: DeckSlot[][] = [
  [
    { id: "tip-flush", kind: "tip", labelKey: "mame.janusDeck.slot.tipFlush" },
    { id: "p1", kind: "source", labelKey: "mame.janusDeck.slot.p1" },
    { id: "p2", kind: "source", labelKey: "mame.janusDeck.slot.p2" },
    { id: "p3", kind: "source", labelKey: "mame.janusDeck.slot.p3" },
  ],
  [
    { id: "waste", kind: "waste", labelKey: "mame.janusDeck.slot.waste" },
    { id: "blank-1", kind: "blank", labelKey: "mame.janusDeck.slot.blank" },
    { id: "blank-2", kind: "blank", labelKey: "mame.janusDeck.slot.blank" },
    { id: "final", kind: "destination", labelKey: "mame.janusDeck.slot.final" },
  ],
];

const SLOT_STYLE: Record<SlotKind, string> = {
  source:
    "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100",
  destination:
    "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100",
  tip: "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-700 dark:bg-sky-950 dark:text-sky-100",
  waste:
    "border-stone-300 bg-stone-50 text-stone-700 dark:border-stone-600 dark:bg-stone-900 dark:text-stone-300",
  blank: "border-dashed border-border bg-muted/30 text-muted-foreground",
};

interface JanusDeckPreviewProps {
  className?: string;
}

export function JanusDeckPreview({ className }: JanusDeckPreviewProps) {
  const { t } = useTranslation();

  return (
    <section
      className={cn("space-y-2", className)}
      aria-label={t("mame.janusDeck.ariaLabel")}
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          {t("mame.janusDeck.title")}
        </h3>
        <span className="text-[11px] text-muted-foreground">
          {t("mame.janusDeck.headFixedNote")}
        </span>
      </header>

      <div
        className="grid gap-1.5 rounded-control border border-border bg-background p-3"
        role="img"
        aria-label={t("mame.janusDeck.deckImageAriaLabel")}
      >
        {DECK_LAYOUT.map((row, rowIdx) => (
          <div key={`row-${rowIdx}`} className="grid grid-cols-4 gap-1.5">
            {row.map((slot) => (
              <div
                key={slot.id}
                className={cn(
                  "flex aspect-[4/3] flex-col items-center justify-center rounded-control border-2 px-1 py-1.5 text-center",
                  SLOT_STYLE[slot.kind],
                )}
              >
                <span className="text-[11px] font-medium leading-tight">
                  {t(slot.labelKey)}
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {t("mame.janusDeck.aspDspNote")}
        <br />
        {t("mame.janusDeck.matchByNameNote")}
      </p>
    </section>
  );
}
