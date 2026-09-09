/**
 * Shared Tailwind class strings for the Kuro step-6 export plate previews
 * (EchoPlateView / JanusPlateView / DestPlateView / PlateLegendsPanel).
 *
 * Why a module and not literals in each view: the legend swatches and the
 * grid cells they explain used to carry independent literals, and they drifted
 *, the cells gained `dark:bg-*-500` variants and the swatches did not, so in
 * dark mode the legend named a colour no cell rendered. Both sides now read
 * the same constant, which is also what the tests assert against, so a future
 * colour change cannot split them again.
 *
 * (This file is `.ts`; tailwind.config.js `content` covers
 * `./src/**\/*.{js,ts,jsx,tsx}`, so these class names are still scanned.)
 */

/** Fill of a well holding a forward primer (Echo odd rows, JANUS rack 1). */
export const PLATE_FILL_FORWARD = "bg-blue-400 dark:bg-blue-500";
/** Fill of a well holding a reverse primer (Echo even rows, JANUS rack 2). */
export const PLATE_FILL_REVERSE = "bg-orange-400 dark:bg-orange-500";
/** Destination well where both F and R primers landed. */
export const PLATE_FILL_DEST_COMPLETE = "bg-emerald-400 dark:bg-emerald-500";
/** Destination well where only one of F/R landed. */
export const PLATE_FILL_DEST_PARTIAL = "bg-amber-400 dark:bg-amber-500";

/**
 * Echo source well the selected quadrant pair does not reach: it belongs to
 * the other pair and is held for the next run.
 *
 * Dashed *and* muted, not muted alone: an empty well of the selected pair is
 * also pale, so colour alone would leave the two indistinguishable to a
 * red-green or low-contrast reader. The border style carries the same split.
 */
export const PLATE_FILL_RESERVED = "border-dashed border-border bg-muted/60 dark:bg-muted/40";

/**
 * Frame + scroll container shared by all three preview views.
 *
 * Copied from the class list on WellPlate.tsx's grid wrapper so the step-6
 * previews sit in the same card-on-card frame the rest of the app's plate
 * views do. `p-2.5` follows WellPlate (a dense scrolling grid) rather than
 * PlateMap's `p-3` (an inline-block summary box), because these grids are the
 * former.
 *
 * The element carrying this is the scroller: `min-w-*` belongs on a child, not
 * here, so a grid too wide for the viewport scrolls inside its own frame
 * instead of pushing the page.
 */
export const PLATE_PREVIEW_FRAME =
  "w-full overflow-x-auto rounded-container border border-border/70 bg-card p-2.5";

/** Caption line above a grid (JANUS rack labels, Echo/Dest titles). */
export const PLATE_PREVIEW_LABEL = "text-caption text-muted-foreground mb-1";
