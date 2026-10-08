import { expect } from "vitest";

/**
 * Shared assertions for the three Kuro step-6 plate previews (Echo / JANUS /
 * Dest), which now render their header row, wells and cell popover through
 * `PlatePreviewGrid.tsx`. These live here so all three test files check the
 * same contract; a rule that only one of them asserts is a rule the other two
 * are free to drift away from, which is how the duplication being removed
 * produced three different answers in the first place.
 */

/**
 * The frame/scroller contract these previews share with WellPlate: the
 * outermost element carries the card frame and the horizontal scroll, and
 * `min-w-*` sits on a descendant, so a plate wider than the viewport scrolls
 * inside its own frame instead of pushing the page.
 */
export function expectFramedScroller(
  root: HTMLElement,
  frameClass: string,
  minWidthClass: string,
): void {
  expect(root.className).toContain(frameClass);
  expect(root.className).toContain("overflow-x-auto");
  expect(root.className).not.toMatch(/min-w-/);
  expect(root.querySelector(`.${CSS.escape(minWidthClass)}`)).not.toBeNull();
}

/**
 * ARIA grid shape, asserted identically for all three views.
 *
 * - every `role="row"` exposes only rowheader/columnheader/gridcell children
 *   (the rows use `display: contents`, so its DOM children are the row's ARIA
 *   children);
 * - a filled well is a `<button>` inside a `<div role="gridcell">`, the
 *   WellPlate.tsx:127-134 shape, and the button keeps its native role rather
 *   than being overridden with `role="gridcell"`;
 * - every row header carries a localized `aria-label`.
 */
export function expectGridSemantics(container: HTMLElement, cellTestId: string): void {
  const rows = container.querySelectorAll<HTMLElement>("[role='row']");
  expect(rows.length).toBeGreaterThan(0);
  for (const row of rows) {
    for (const child of Array.from(row.children)) {
      const role = child.getAttribute("role");
      // The header row opens with an unlabelled corner spacer, which carries
      // no role on purpose (it names neither a column nor a row).
      if (role === null && child.childElementCount === 0 && child.textContent === "") continue;
      expect(role).toMatch(/^(rowheader|columnheader|gridcell)$/);
    }
  }

  const headers = container.querySelectorAll<HTMLElement>("[role='rowheader']");
  expect(headers.length).toBeGreaterThan(0);
  for (const h of headers) {
    expect(h.getAttribute("aria-label")).toBeTruthy();
  }

  const buttons = container.querySelectorAll<HTMLElement>(`button[data-testid='${cellTestId}']`);
  for (const b of buttons) {
    expect(b.getAttribute("role")).toBeNull();
    expect(b.parentElement?.getAttribute("role")).toBe("gridcell");
  }
}

/** Grid track template must stay byte-identical to the tuned value. */
export function expectGridTemplate(container: HTMLElement, expected: string): void {
  const grids = container.querySelectorAll<HTMLElement>("[role='grid']");
  expect(grids.length).toBeGreaterThan(0);
  for (const g of grids) {
    expect(g.style.gridTemplateColumns).toBe(expected);
  }
}

/**
 * The per-view cell size class is a prop, not something the shared component
 * picks: index.css clamps font size through three different classes and one
 * shared class would collapse three tuned clamps into one.
 */
export function expectCellSizeClass(
  filled: HTMLElement,
  expected: string,
  forbidden: readonly string[],
): void {
  const classes = filled.className.split(/\s+/);
  expect(classes).toContain(expected);
  for (const f of forbidden) {
    expect(classes).not.toContain(f);
  }
}
