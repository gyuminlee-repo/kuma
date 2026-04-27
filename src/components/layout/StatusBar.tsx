import { useAppStore } from "../../store/appStore";
import { GlobalStatusBar } from "./GlobalStatusBar";

/**
 * kuro 상태바.
 * GlobalStatusBar 셸을 사용하며, 기존 sidecarStatus 문자열을
 * GlobalStatusBar의 SidecarInfo로 매핑한다.
 */
export function StatusBar({ sidecarStatus, onRetry }: { sidecarStatus: string; onRetry: () => void }) {
  const statusMessage = useAppStore((s) => s.statusMessage);

  const sidecarState: "ready" | "connecting" | "error" =
    sidecarStatus === "ready"
      ? "ready"
      : sidecarStatus === "connecting"
        ? "connecting"
        : "error";

  const sidecarLabel =
    sidecarStatus === "ready"
      ? "Ready"
      : sidecarStatus === "connecting"
        ? "Connecting"
        : "Sidecar failed";

  return (
    <GlobalStatusBar
      message={statusMessage}
      sidecar={{
        state: sidecarState,
        label: sidecarLabel,
        onRetry: sidecarState === "error" ? onRetry : undefined,
      }}
    />
  );
}
