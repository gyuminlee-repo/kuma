import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { WifiOff } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { GlobalStatusBar } from "./GlobalStatusBar";
import { rpc } from "../../lib/ipc";

/** §2 Observability: health_info polling interval (ms). */
const HEALTH_POLL_INTERVAL = 30_000;

interface HealthInfo {
  pid: number;
  rss_bytes: number;
  py_version: string;
}

interface StatusBarProps {
  sidecarStatus: string;
  onRetry: () => void;
  /**
   * AppLayout에서 계산된 네트워크 에러 분류 결과.
   * "network"일 때 WifiOff 아이콘을 statusbar 좌측 메시지 앞에 표시.
   */
  statusErrorKind?: string | null;
}

/**
 * kuro 상태바.
 * GlobalStatusBar 셸을 사용하며, 기존 sidecarStatus 문자열을
 * GlobalStatusBar의 SidecarInfo로 매핑한다.
 * §2 Observability: ready 상태에서 30초마다 health_info RPC 폴링 → tooltip에 PID + RSS 표시.
 * statusErrorKind="network" 시 WifiOff 아이콘을 메시지 앞에 동반 (접근성: 색 단독 금지 §6.2).
 */
export function StatusBar({ sidecarStatus, onRetry, statusErrorKind }: StatusBarProps) {
  const { t } = useTranslation();
  const statusMessage = useAppStore((s) => s.statusMessage);
  const [healthInfo, setHealthInfo] = useState<HealthInfo | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // §2: Poll health_info when sidecar is ready.
  useEffect(() => {
    if (sidecarStatus !== "ready") {
      setHealthInfo(null);
      return;
    }

    async function fetchHealth() {
      try {
        const info = await rpc<HealthInfo>("kuro", "health_info", {});
        setHealthInfo(info);
      } catch (err) {
        // Non-critical: sidecar may be mid-restart. Clear stale data so tooltip
        // does not show outdated PID/RSS after a sidecar cycle.
        console.warn("[StatusBar] health_info polling failed:", err);
        setHealthInfo(null);
      }
    }

    void fetchHealth();
    timerRef.current = setInterval(() => { void fetchHealth(); }, HEALTH_POLL_INTERVAL);

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [sidecarStatus]);

  const sidecarState: "ready" | "connecting" | "error" =
    sidecarStatus === "ready"
      ? "ready"
      : sidecarStatus === "connecting"
        ? "connecting"
        : "error";

  const sidecarLabel =
    sidecarStatus === "ready"
      ? t("statusBar.ready")
      : sidecarStatus === "connecting"
        ? t("statusBar.connecting")
        : t("statusBar.failed");

  return (
    <GlobalStatusBar
      message={statusMessage}
      sidecar={{
        state: sidecarState,
        label: sidecarLabel,
        onRetry: sidecarState === "error" ? onRetry : undefined,
        pid: healthInfo?.pid,
        rssMb: healthInfo !== null ? healthInfo.rss_bytes / (1024 * 1024) : undefined,
      }}
      centerSlot={
        statusErrorKind === "network" ? (
          <span
            className="flex items-center gap-1 text-amber-500 dark:text-amber-400"
            aria-label={t("statusBar.networkError")}
          >
            <WifiOff size={12} aria-hidden="true" />
          </span>
        ) : undefined
      }
    />
  );
}
