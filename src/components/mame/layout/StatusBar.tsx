import { useAppStore } from "@/store/mame/mameAppStore";
import type { SidecarStatus } from "@/types/mame/models";
import { cn } from "@/lib/utils";

const statusLabel: Record<SidecarStatus, string> = {
  disconnected: "Disconnected",
  connecting: "Connecting",
  ready: "Ready",
  error: "Error",
};

export function StatusBar({
  sidecarStatus,
  onRetry,
}: {
  sidecarStatus: SidecarStatus;
  onRetry: () => void;
}) {
  const analyzeMessage = useAppStore((state) => state.analyzeMessage);
  const summary = useAppStore((state) => state.summary);

  return (
    <footer
      className="flex h-statusbar flex-shrink-0 items-center gap-3 border-t border-border bg-muted/40 px-4 text-2xs text-muted-foreground"
      role="contentinfo"
      aria-label="Status bar"
    >
      <span className="min-w-0 flex-1 truncate" aria-live="polite">
        {analyzeMessage}
      </span>

      {summary && (
        <span className="whitespace-nowrap tabular-nums">
          Total {summary.total} · PASS {summary.pass_count} · Ambiguous{" "}
          {summary.ambiguous_count} · Fail {summary.fail_count}
        </span>
      )}

      {sidecarStatus === "error" && (
        <span className="inline-flex items-center gap-1 rounded-full bg-[var(--status-error)] px-2 py-0.5 text-[10px] font-medium text-white">
          Sidecar unavailable
          <button
            type="button"
            className="font-semibold underline hover:opacity-80"
            onClick={onRetry}
            aria-label="Retry sidecar connection"
          >
            Retry
          </button>
        </span>
      )}

      <span className="whitespace-nowrap">{statusLabel[sidecarStatus]}</span>

      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full flex-shrink-0",
          sidecarStatus === "ready"
            ? "bg-[var(--status-ready)]"
            : sidecarStatus === "connecting"
              ? "bg-[var(--status-connecting)]"
              : "bg-[var(--status-error)]",
        )}
        role="status"
        aria-label={`Sidecar: ${sidecarStatus}`}
        title={`Sidecar: ${sidecarStatus}`}
      />
    </footer>
  );
}
