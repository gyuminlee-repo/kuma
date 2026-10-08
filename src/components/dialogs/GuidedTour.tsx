import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useFocusTrap } from "@/hooks/useFocusTrap";

export interface GuidedTourStep {
  target: string;
  titleKey: string;
  bodyKey: string;
}

interface GuidedTourProps {
  steps: GuidedTourStep[];
  onComplete: () => void;
  onSkip: () => void;
  onDismiss: () => void;
}

interface HighlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const HIGHLIGHT_PADDING = 6;

export function GuidedTour({ steps, onComplete, onSkip, onDismiss }: GuidedTourProps) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<HighlightRect | null>(null);
  const cardRef = useFocusTrap<HTMLElement>();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const step = steps[index];
  const isLast = index === steps.length - 1;

  const goForward = useCallback(() => {
    if (isLast) onComplete();
    else setIndex((value) => value + 1);
  }, [isLast, onComplete]);

  useEffect(() => {
    setIndex(0);
  }, [steps]);

  useEffect(() => {
    if (!step) return;

    let frame = 0;
    let observedTarget: HTMLElement | null = null;
    let resizeObserver: ResizeObserver;
    let mutationObserver: MutationObserver;
    const updateRect = () => {
      const target = document.querySelector<HTMLElement>(step.target);
      if (!target) {
        setRect(null);
        return;
      }
      mutationObserver.disconnect();
      if (target !== observedTarget) {
        resizeObserver.disconnect();
        resizeObserver.observe(target);
        observedTarget = target;
      }
      const bounds = target.getBoundingClientRect();
      setRect({
        top: Math.max(0, bounds.top - HIGHLIGHT_PADDING),
        left: Math.max(0, bounds.left - HIGHLIGHT_PADDING),
        width: Math.min(window.innerWidth, bounds.width + HIGHLIGHT_PADDING * 2),
        height: Math.min(window.innerHeight, bounds.height + HIGHLIGHT_PADDING * 2),
      });
    };
    resizeObserver = new ResizeObserver(updateRect);
    mutationObserver = new MutationObserver(updateRect);
    mutationObserver.observe(document.body, { childList: true, subtree: true });
    frame = requestAnimationFrame(updateRect);
    window.addEventListener("resize", updateRect);
    const missingTargetTimer = setTimeout(() => {
      if (!document.querySelector(step.target)) {
        console.warn(`[GuidedTour] target not found; skipping step: ${step.target}`);
        goForward();
      }
    }, 4_000);

    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(missingTargetTimer);
      mutationObserver.disconnect();
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateRect);
    };
  }, [goForward, step]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onDismiss]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [index]);

  useEffect(() => {
    const appRoot = document.getElementById("root");
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden") ?? null;
    if (appRoot) {
      appRoot.inert = true;
      appRoot.setAttribute("aria-hidden", "true");
    }
    return () => {
      if (appRoot) {
        appRoot.inert = false;
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      previousFocus?.focus();
    };
  }, []);

  const highlightStyle = useMemo(() => {
    if (!rect) return undefined;
    return {
      top: rect.top,
      left: rect.left,
      width: rect.width,
      height: rect.height,
      boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.68)",
    };
  }, [rect]);

  if (!step) return null;

  return createPortal(
    <div className="fixed inset-0 z-[80] pointer-events-none">
      <div
        className={`fixed inset-0 pointer-events-auto ${rect ? "" : "bg-slate-950/70"}`}
        aria-hidden="true"
      />
      {rect && (
        <div
          className="fixed rounded-lg border-2 border-info bg-transparent shadow-lg transition-all duration-200"
          style={highlightStyle}
          aria-hidden="true"
        />
      )}
      <section
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guided-tour-title"
        aria-describedby="guided-tour-body"
        className={`pointer-events-auto fixed bottom-6 w-[min(360px,calc(100vw-3rem))] rounded-xl border border-border bg-card p-5 text-card-foreground shadow-2xl ${step.target.includes("inspector") ? "left-6" : "right-6"}`}
      >
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("phaseE.wizard.progress", { current: index + 1, total: steps.length })}
        </p>
        <div aria-live="polite">
          <h2
            ref={headingRef}
            id="guided-tour-title"
            tabIndex={-1}
            className="mt-2 text-lg font-semibold outline-none"
          >
          {t(step.titleKey)}
          </h2>
          <p id="guided-tour-body" className="mt-2 text-sm leading-6 text-muted-foreground">
          {t(step.bodyKey)}
          </p>
        </div>
        <div className="mt-5 flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onSkip}>
            {t("guidedTour.skip")}
          </Button>
          <div className="flex-1" />
          {index > 0 && (
            <Button size="sm" variant="outline" onClick={() => setIndex((value) => value - 1)}>
              {t("phaseE.wizard.back")}
            </Button>
          )}
          <Button
            size="sm"
            onClick={goForward}
          >
            {isLast ? t("guidedTour.finish") : t("phaseE.wizard.next")}
          </Button>
        </div>
      </section>
    </div>,
    document.body,
  );
}
