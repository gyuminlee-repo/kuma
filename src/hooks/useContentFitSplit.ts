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
 * Deliberately does nothing for a layout the operator dragged, reported through
 * `onDragging`; their split is a decision, not a default to recompute. A drag is
 * recorded under its own key so the decision survives a restart.
 *
 * That flag is deliberately not read off the `autoSaveId` entry, which was the
 * first attempt and was wrong. react-resizable-panels persists on every layout
 * change, including the default it applies on mount, so the entry exists for
 * anyone who has merely opened the view. Treating it as a decision meant the fit
 * never ran for any operator who had opened step 2.2 on an earlier build, which
 * is every operator who had used the step at all, and reinstalling the app does
 * not clear it because the store lives in the webview profile rather than in the
 * installed files (2026-08-06).
 */
import { useCallback, useEffect, useRef } from "react";
import type { ImperativePanelGroupHandle } from "react-resizable-panels";

/** Where a recorded drag is kept, keyed per group. */
const SIZED_PREFIX = "kuma.contentFitSplit.userSized:";

/**
 * Has the operator sized this group themselves, in this session or an earlier one?
 *
 * Only a recorded drag counts. The `react-resizable-panels:` entry for the same
 * group does not, however tempting it looks: the library writes it on mount for
 * the default layout too, so it marks a view that was opened, not a size that was
 * chosen.
 */
export function hasOperatorChoice(autoSaveId: string): boolean {
  try {
    return localStorage.getItem(`${SIZED_PREFIX}${autoSaveId}`) !== null;
  } catch {
    // Storage can be unavailable (private mode, a locked-down webview). Fitting
    // by content is still better than the fixed ratio, so carry on.
    return false;
  }
}

/** Record that the operator dragged this group, so later sessions leave it alone. */
export function rememberOperatorChoice(autoSaveId: string): void {
  try {
    localStorage.setItem(`${SIZED_PREFIX}${autoSaveId}`, "1");
  } catch {
    // The drag still holds for this session; only its survival is lost.
  }
}

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
  /** Identifies the group, so a drag recorded earlier is left alone. */
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

  const onDragging = useCallback(
    (isDragging: boolean) => {
      if (!isDragging) return;
      operatorChose.current = true;
      rememberOperatorChoice(autoSaveId);
    },
    [autoSaveId],
  );

  useEffect(() => {
    // A drag recorded earlier is the same decision, made in a previous session.
    if (hasOperatorChoice(autoSaveId)) operatorChose.current = true;
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
