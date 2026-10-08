/**
 * useColorblindMode — reads the kuro colorblind-assist toggle from localStorage
 * and subscribes to runtime changes dispatched via the custom DOM event
 * "kuma:colorblindMode".
 *
 * Storage key : "kuma:kuro:colorblindMode"
 * Dispatch    : new CustomEvent("kuma:colorblindMode", { detail: boolean })
 */
import { useEffect, useState } from "react";

const CB_KEY = "kuma:kuro:colorblindMode";

export function useColorblindMode(): boolean {
  const [enabled, setEnabled] = useState<boolean>(
    () => localStorage.getItem(CB_KEY) === "true",
  );

  useEffect(() => {
    function handler(e: Event) {
      const detail = (e as CustomEvent<boolean>).detail;
      setEnabled(Boolean(detail));
    }
    window.addEventListener("kuma:colorblindMode", handler);
    return () => window.removeEventListener("kuma:colorblindMode", handler);
  }, []);

  return enabled;
}
