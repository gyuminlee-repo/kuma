import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { SidecarStatus } from "@/types/mame/models";
import { GlobalStatusBar } from "@/components/layout/GlobalStatusBar";
import type { SidecarInfo } from "@/components/layout/GlobalStatusBar";

/**
 * mame SidecarStatus → GlobalStatusBar SidecarInfo 매핑.
 *
 * mame는 "disconnected" 상태를 별도로 가진다.
 * GlobalStatusBar는 ready/connecting/error 3종만 지원하므로,
 * disconnected는 "error"로 매핑해 retry를 유도한다.
 * // TODO(plan): mame가 disconnected → connecting 자동 재연결 로직을 추가하면
 *               별도 "disconnected" state를 GlobalStatusBar에 4번째로 추가 고려.
 */
function mapSidecarState(
  status: SidecarStatus,
  onRetry: () => void,
): SidecarInfo {
  switch (status) {
    case "ready":
      return { state: "ready", label: "Ready" };
    case "connecting":
      return { state: "connecting", label: "Connecting" };
    case "error":
      return { state: "error", label: "Sidecar error", onRetry };
    case "disconnected":
      return { state: "error", label: "Disconnected", onRetry };
  }
}

/**
 * mame 상태바.
 * GlobalStatusBar 셸을 사용하며, 기존 빨간 pill 에러 표현과
 * `--status-*` 미정의 변수를 제거한다.
 * 요약 수치는 centerSlot으로 전달한다.
 */
export function StatusBar({
  sidecarStatus,
  onRetry,
}: {
  sidecarStatus: SidecarStatus;
  onRetry: () => void;
}) {
  const analyzeMessage = useMameAppStore((state) => state.analyzeMessage);
  const summary = useMameAppStore((state) => state.summary);

  const centerSlot = summary ? (
    <span className="tabular-nums">
      Total {summary.total} · PASS {summary.pass_count} · Ambiguous{" "}
      {summary.ambiguous_count} · Fail {summary.fail_count}
    </span>
  ) : undefined;

  return (
    <GlobalStatusBar
      message={analyzeMessage}
      centerSlot={centerSlot}
      sidecar={mapSidecarState(sidecarStatus, onRetry)}
    />
  );
}
