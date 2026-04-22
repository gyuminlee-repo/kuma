import { useMemo } from "react";
import { useAppStore } from "../../store/appStore";
import { Progress } from "../ui/progress";

export function StatusBar({ sidecarStatus, onRetry }: { sidecarStatus: string; onRetry: () => void }) {
  const isDesigning = useAppStore((s) => s.isDesigning);
  const progress = useAppStore((s) => s.progress);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const designResults = useAppStore((s) => s.designResults);

  const tmOkCount = useMemo(
    () => designResults.filter((r) => r.tm_condition_met).length,
    [designResults],
  );

  return (
    <div className="flex items-center gap-3 border-t border-slate-200/80 bg-white/70 px-5 py-2 text-xs text-slate-600 backdrop-blur">
      <span className="flex-1 truncate font-medium text-slate-700">{statusMessage}</span>
      {totalCount > 0 && (
        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] text-slate-600">
          {successCount}/{totalCount} designed | Tm OK: {tmOkCount}/
          {successCount}
        </span>
      )}
      {isDesigning && <Progress value={progress} className="h-2 w-36" />}
      {sidecarStatus === "error" && (
        <span className="inline-flex items-center gap-1 rounded-full bg-red-600 px-3 py-1 text-[10px] text-white whitespace-nowrap">
          Sidecar connection failed.
          <button
            className="underline font-semibold hover:text-red-200"
            onClick={onRetry}
          >
            Retry
          </button>
        </span>
      )}
      <span
        className={`h-2.5 w-2.5 rounded-full flex-shrink-0 ${
          sidecarStatus === "ready"
            ? "bg-green-500"
            : sidecarStatus === "connecting"
              ? "bg-yellow-500"
              : "bg-red-500"
        }`}
        role="status"
        aria-label={`Sidecar: ${sidecarStatus}`}
        title={`Sidecar: ${sidecarStatus}`}
      />
    </div>
  );
}
