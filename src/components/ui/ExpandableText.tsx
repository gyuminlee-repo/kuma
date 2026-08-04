/**
 * ExpandableText, single-line (truncated) text with a real way to read the rest.
 *
 * Table cells clip long strings, and a native `title=` tooltip is not a usable
 * escape hatch: it waits ~1s before appearing, never opens from the keyboard,
 * and renders one unwrapped line that the browser clips at the viewport edge.
 * This component keeps the clipping but replaces that path with a toggled
 * panel, following the existing InlineHelp convention (portal into
 * document.body + fixed position recomputed on scroll/resize) rather than
 * introducing a tooltip library.
 *
 * The trigger only appears when the text actually overflows its box, measured
 * with scrollWidth vs clientWidth (re-measured through a ResizeObserver, so a
 * resized column flips the trigger on or off by itself). Short cells stay plain
 * spans with no extra interactive element.
 *
 * Usage:
 *   <ExpandableText text={notes} label={columnLabel} className="text-xs" />
 *   <ExpandableText text={plain} label={columnLabel}>{inlineNodes}</ExpandableText>
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
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

/** Panel geometry (px). Wide enough for a wrapped sentence, clamped to viewport. */
const PANEL_WIDTH = 360;
const PANEL_MARGIN = 8;
/** Sub-pixel slack so a 1px rounding difference is not read as overflow. */
const OVERFLOW_SLACK = 1;

interface ExpandableTextProps {
  /** Full text: the accessible name, and what the panel shows. */
  text: string;
  /** Translated column/field name, used to say what the panel belongs to. */
  label: string;
  /** Classes applied to the rendered element (span or button). */
  className?: string;
  /** Optional rich inline rendering; defaults to `text`. */
  children?: ReactNode;
}

export function ExpandableText({ text, label, className, children }: ExpandableTextProps) {
  const { t } = useTranslation();
  const [overflowing, setOverflowing] = useState(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const nodeRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const panelId = useId();

  const measure = useCallback(() => {
    const el = nodeRef.current;
    if (!el) return;
    setOverflowing(el.scrollWidth > el.clientWidth + OVERFLOW_SLACK);
  }, []);

  // Ref callback (not an effect): the measured node is a <span> or a <button>
  // depending on `overflowing`, so it is replaced when the state flips. Wiring
  // the observer here re-attaches it to whichever node is currently mounted.
  const attach = useCallback(
    (node: HTMLElement | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      nodeRef.current = node;
      if (!node) return;
      measure();
      if (typeof ResizeObserver !== "undefined") {
        const observer = new ResizeObserver(() => measure());
        observer.observe(node);
        observerRef.current = observer;
      }
    },
    [measure],
  );

  useEffect(() => {
    if (!open) return;
    const update = () => {
      const rect = nodeRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition({
        top: Math.max(PANEL_MARGIN, Math.min(rect.bottom + 4, window.innerHeight - PANEL_MARGIN)),
        left: Math.max(
          PANEL_MARGIN,
          Math.min(rect.left, window.innerWidth - PANEL_WIDTH - PANEL_MARGIN),
        ),
      });
    };
    update();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Node && nodeRef.current?.contains(target)) return;
      setOpen(false);
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
  }, [open]);

  // A widened column can remove the overflow (and the trigger) while the panel
  // is open; drop the open state with it so it cannot reappear on its own.
  useEffect(() => {
    if (!overflowing && open) setOpen(false);
  }, [overflowing, open]);

  const inline = children ?? text;

  if (!overflowing) {
    return (
      <span ref={attach} className={cn("block truncate", className)}>
        {inline}
      </span>
    );
  }

  const labelKey = open ? "ui.expandableText.hide" : "ui.expandableText.show";

  return (
    <>
      <button
        ref={attach}
        type="button"
        aria-label={t(labelKey, { label, text })}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={(event: ReactKeyboardEvent<HTMLButtonElement>) => {
          // The table header/row handlers must not react to a cell expansion.
          event.stopPropagation();
        }}
        className={cn(
          "block w-full min-w-0 truncate rounded-control text-left underline decoration-dotted underline-offset-2",
          "hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
          className,
        )}
      >
        {inline}
      </button>
      {open &&
        position &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            id={panelId}
            role="tooltip"
            data-testid="expandable-text-panel"
            className="fixed z-[100] max-h-[50vh] overflow-auto whitespace-pre-wrap break-words rounded-control border border-border bg-popover px-3 py-2 text-xs leading-relaxed text-popover-foreground shadow-lg"
            style={{ top: position.top, left: position.left, width: PANEL_WIDTH }}
          >
            <span className="mb-1 block text-caption font-semibold text-muted-foreground">
              {label}
            </span>
            {text}
          </div>,
          document.body,
        )}
    </>
  );
}
