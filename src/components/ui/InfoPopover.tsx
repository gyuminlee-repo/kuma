/**
 * InfoPopover, a click-opened explanation panel anchored to an inline label.
 *
 * Same mechanics as ExpandableText (portal into document.body + fixed position
 * recomputed on scroll/resize, Escape close, outside-click close), for the
 * other half of that problem: ExpandableText exists to show text that was
 * clipped, so its trigger appears only when the inline content overflows. A
 * short number never overflows, yet the reader still needs somewhere to ask
 * what the number means. This component always renders its trigger and takes
 * arbitrary panel content instead of one string, which is what separates it
 * from InlineHelp (a flat string, and neither Escape nor outside-click close).
 *
 * Click, not hover, is deliberate: the panel holds several sentences a reader
 * scans back and forth over, and a hover panel disappears the moment the
 * pointer leaves the trigger. It also gives keyboard and touch users the same
 * affordance without a separate path.
 *
 * The portal is what lets this be used inside a fixed-width, overflow-hidden
 * column: the panel is positioned against the viewport, so it is sized for
 * reading rather than for the column it is anchored in.
 *
 * Usage: pass an already-translated `label` and `ariaLabel`, plus the panel
 * body as children. Translation stays with the caller so this file owns no
 * locale keys of its own. (Written prose rather than a code sample on purpose:
 * `scripts/i18n-lint.mjs` reads comments too, and a sample call in here is
 * indistinguishable from a real one with a key nobody ever added.)
 */
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

/** Panel geometry (px). Wide enough for a wrapped sentence, clamped to viewport. */
const DEFAULT_PANEL_WIDTH = 320;
const PANEL_MARGIN = 8;
/** Gap between the trigger and the panel edge. */
const PANEL_GAP = 4;
/**
 * Room below the trigger under which the panel flips above it. A trigger near
 * the bottom of a tall scrolling column would otherwise open into a few pixels
 * of viewport, which is a panel the reader has to scroll to read a sentence.
 */
const MIN_SPACE_BELOW = 200;

/**
 * Anchored either from the top (opening downwards) or from the bottom (opening
 * upwards). Anchoring the bottom edge is what makes the upward case work
 * without measuring the panel first: CSS resolves the height.
 */
interface PanelPosition {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

/**
 * `link` puts the label itself on screen as the trigger. `icon` hides it and
 * shows a round "?" instead, for a field whose visible label is already the
 * form label next to it: repeating that label as a second piece of underlined
 * text reads as a second field rather than as help for the first. The label is
 * still the panel heading and still part of the accessible name.
 */
type InfoPopoverVariant = "link" | "icon";

interface InfoPopoverProps {
  /** Visible trigger text (variant `link`), and the panel heading in both. */
  label: string;
  /** Accessible name for the trigger button. Says what will be explained. */
  ariaLabel: string;
  /** Panel body. */
  children: ReactNode;
  /** Classes applied to the trigger button. */
  className?: string;
  /** Test hook on the panel; the trigger carries `${testId}-trigger`. */
  testId?: string;
  /** Trigger shape. Defaults to the inline text link. */
  variant?: InfoPopoverVariant;
  /**
   * Panel width in px. A panel holding a table needs more room than one
   * holding a sentence, and the width has to be known before the panel is
   * laid out because the horizontal clamp above is computed from it.
   */
  width?: number;
}

export function InfoPopover({
  label,
  ariaLabel,
  children,
  className,
  testId = "info-popover",
  variant = "link",
  width = DEFAULT_PANEL_WIDTH,
}: InfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const panelId = useId();

  const close = useCallback((refocus: boolean) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const update = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const left = Math.max(
        PANEL_MARGIN,
        Math.min(rect.left, window.innerWidth - width - PANEL_MARGIN),
      );
      const spaceBelow = window.innerHeight - rect.bottom - PANEL_GAP - PANEL_MARGIN;
      const spaceAbove = rect.top - PANEL_GAP - PANEL_MARGIN;
      if (spaceBelow < MIN_SPACE_BELOW && spaceAbove > spaceBelow) {
        setPosition({
          left,
          bottom: window.innerHeight - rect.top + PANEL_GAP,
          maxHeight: Math.max(0, spaceAbove),
        });
      } else {
        setPosition({
          left,
          top: rect.bottom + PANEL_GAP,
          maxHeight: Math.max(0, spaceBelow),
        });
      }
    };
    update();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(true);
    };
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      // Clicking the trigger is handled by its own onClick (which toggles), and
      // a click inside the panel is a reader selecting text, not a dismissal.
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      close(false);
    };
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, close, width]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        data-testid={`${testId}-trigger`}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(event: ReactKeyboardEvent<HTMLButtonElement>) => {
          // Escape is closed here rather than left to the document listener
          // above. React's synthetic stopPropagation also stops the NATIVE
          // event, and React 19 attaches its listener at the root container,
          // so a keystroke that starts on this button never reaches
          // `document` (verified against react-dom 19 + jsdom). The trigger
          // holds focus for exactly the reader who needs Escape: it is
          // focused after opening from the keyboard, and `close(true)`
          // deliberately puts focus back on it.
          if (event.key === "Escape" && open) close(true);
          // An enclosing row/table handler must not react to opening a panel.
          event.stopPropagation();
        }}
        className={cn(
          "rounded-control focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
          variant === "icon"
            ? [
                "inline-flex h-4 w-4 items-center justify-center rounded-full",
                "text-plate-tiny font-bold leading-none transition-colors",
                "bg-muted text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              ]
            : [
                "text-left underline decoration-dotted underline-offset-2",
                "hover:text-foreground",
              ],
          className,
        )}
      >
        {variant === "icon" ? "?" : label}
      </button>
      {open &&
        position &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            id={panelId}
            data-testid={testId}
            className="fixed z-[100] overflow-auto break-words rounded-control border border-border bg-popover px-3 py-2 text-xs leading-relaxed text-popover-foreground shadow-lg"
            style={{
              left: position.left,
              top: position.top,
              bottom: position.bottom,
              width,
              maxHeight: position.maxHeight,
            }}
          >
            <span className="mb-1 block text-caption font-semibold text-muted-foreground">
              {label}
            </span>
            {children}
          </div>,
          document.body,
        )}
    </>
  );
}
