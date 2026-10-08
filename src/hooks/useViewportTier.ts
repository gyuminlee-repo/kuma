import { useEffect, useState } from "react";

/**
 * Viewport height tier.
 *
 * The KURO/MAME shell spends a fixed vertical budget before a step body gets
 * any space (app chrome, sequence viewer slot, drawer strip, wizard header and
 * footer). On short windows that budget starves the step body until panels are
 * no longer discoverable. The tier lets the shell reclaim space instead.
 *
 * Threshold derivation (measured, width 1440, Playwright):
 *   plate grid box height = viewport - 741
 * A full 8-row plate needs 316px, so 1057px of viewport clears it untouched.
 * Collapsing the sequence viewer slot returns ~145px, which moves that figure
 * to ~912. Below 848 the step body can no longer show a plate row without the
 * reclaim, so that is the tight boundary.
 */
export type ViewportTier = "roomy" | "tight";

const TIGHT_QUERY = "(max-height: 847px)";

function readTier(): ViewportTier {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "roomy";
  }
  return window.matchMedia(TIGHT_QUERY).matches ? "tight" : "roomy";
}

/**
 * Subscribes to the tight-height media query. matchMedia fires only when the
 * threshold is crossed, so sidebar drags and splitter drags do not re-render
 * the shell the way a ResizeObserver would.
 */
export function useViewportTier(): ViewportTier {
  const [tier, setTier] = useState<ViewportTier>(readTier);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(TIGHT_QUERY);
    const onChange = () => setTier(mql.matches ? "tight" : "roomy");
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return tier;
}
