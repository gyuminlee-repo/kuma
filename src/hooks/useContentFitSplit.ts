/**
 * Split a two-panel PanelGroup by what each panel needs, not by a fixed ratio.
 *
 * A percentage split has no idea how tall its panels want to be. On step 2.2 the
 * plate map wants 600 to 790 px (eight rows and a well inspector) and the verdict
 * breakdown wants around 500 px, and a hard 34/66 handed the smaller share to the
 * one that needed more: the plate grid scrolled from row D down on every window
 * size measured (381 px hidden at 1920x1080, 442 px at 2560x1440) while the panel
 * underneath had space left over. A scrollbar is worth having, but not while the
 * neighbour leaves room unused (2026-08-05).
 *
 * The rule is the obvious one. When both panels fit, the first takes exactly what
 * it needs and the rest goes to the second. When they do not both fit, the
 * shortfall is shared in proportion to what each asked for, so neither is starved
 * by a number written in the source.
 *
 * Deliberately does nothing in two cases:
 *   - a layout the operator dragged, reported through `onDragging`; their split
 *     is a decision, not a default to recompute.
 *   - a layout `autoSaveId` already restored, which is the same decision from an
 *     earlier session.
 */
import { useCallback, useEffect, useRef } from "react";
import type { ImperativePanelGroupHandle } from "react-resizable-panels";

/** Where react-resizable-panels keeps an `autoSaveId` layout. */
const STORAGE_PREFIX = "react-resizable-panels:";

/**
 * Height this section would need to show everything it holds.
 *
 * Panel bodies scroll internally, so the section's own `scrollHeight` reports the
 * visible height and says nothing about what is cut off. Reading the inner
 * scroller and adding back the chrome around it gives the height that would leave
 * nothing hidden.
 */
function naturalHeight(section: HTMLElement | null): number {
  if (!section) return 0;
  let hidden = 0;
  for (const el of section.querySelectorAll<HTMLElement>("*")) {
    const overflowY = getComputedStyle(el).overflowY;
    if (overflowY !== "auto" && overflowY !== "scroll") continue;
    hidden = Math.max(hidden, el.scrollHeight - el.clientHeight);
  }
  return section.clientHeight + hidden;
}

/**
 * Share of the group the first panel should get, in percent.
 *
 * Both fit: the first takes exactly what it needs and the rest goes to the
 * second. Neither fits: the shortfall is shared in proportion to what each asked
 * for, so a panel is never starved by a number written in the source. The
 * clamps are the two panels' own `minSize`, so the answer is always a share the
 * group would accept.
 */
export function fitShare(
  wantFirst: number,
  wantSecond: number,
  available: number,
  minFirst: number,
  minSecond: number,
): number {
  const share =
    wantFirst + wantSecond <= available
      ? wantFirst / available
      : wantFirst / (wantFirst + wantSecond);
  return Math.min(Math.max(share * 100, minFirst), 100 - minSecond);
}

export interface ContentFitSplitOptions {
  /** Smallest share the first panel may be given, in percent. */
  minFirst: number;
  /** Smallest share the second panel may be given, in percent. */
  minSecond: number;
  /** `autoSaveId` of the group, so a restored layout is left alone. */
  autoSaveId: string;
  /** Recompute when these change (data that alters how tall a panel wants to be). */
  deps: readonly unknown[];
}

export interface ContentFitSplit {
  groupRef: React.RefObject<ImperativePanelGroupHandle | null>;
  firstRef: React.RefObject<HTMLDivElement | null>;
  secondRef: React.RefObject<HTMLDivElement | null>;
  /** Pass to the group's PanelResizeHandle: a drag ends the automatic fitting. */
  onDragging: (isDragging: boolean) => void;
}

export function useContentFitSplit({
  minFirst,
  minSecond,
  autoSaveId,
  deps,
}: ContentFitSplitOptions): ContentFitSplit {
  const groupRef = useRef<ImperativePanelGroupHandle | null>(null);
  const firstRef = useRef<HTMLDivElement | null>(null);
  const secondRef = useRef<HTMLDivElement | null>(null);
  const operatorChose = useRef(false);

  const onDragging = useCallback((isDragging: boolean) => {
    if (isDragging) operatorChose.current = true;
  }, []);

  useEffect(() => {
    // A restored layout is a choice made earlier; treat it like a drag.
    try {
      if (localStorage.getItem(`${STORAGE_PREFIX}${autoSaveId}`) !== null) {
        operatorChose.current = true;
      }
    } catch {
      // Storage can be unavailable (private mode, a locked-down webview). Fitting
      // by content is still better than the fixed ratio, so carry on.
    }
  }, [autoSaveId]);

  useEffect(() => {
    const first = firstRef.current;
    const second = secondRef.current;
    if (!first || !second) return;

    function fit() {
      if (operatorChose.current) return;
      const group = groupRef.current;
      if (!group || !first || !second) return;
      const available = first.clientHeight + second.clientHeight;
      if (available <= 0) return;

      const wantFirst = naturalHeight(first);
      const wantSecond = naturalHeight(second);
      if (wantFirst <= 0 || wantSecond <= 0) return;

      const percent = fitShare(wantFirst, wantSecond, available, minFirst, minSecond);
      const current = group.getLayout();
      // Layout writes re-render the group, so an unconditional write here would
      // feed the ResizeObserver below back into itself.
      if (current.length === 2 && Math.abs(current[0] - percent) < 0.5) return;
      group.setLayout([percent, 100 - percent]);
    }

    // Two passes on mount: the first measures before late content (a chart, a
    // virtualised table) has laid itself out, and the observer catches the rest.
    const raf = requestAnimationFrame(fit);
    const observer = new ResizeObserver(() => fit());
    observer.observe(first);
    observer.observe(second);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minFirst, minSecond, ...deps]);

  return { groupRef, firstRef, secondRef, onDragging };
}
