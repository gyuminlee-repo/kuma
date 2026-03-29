import { useAppStore } from "../../store/appStore";
import { Progress } from "../ui/progress";

export function StatusBar({ sidecarStatus, onRetry }: { sidecarStatus: string; onRetry: () => void }) {
  const isDesigning = useAppStore((s) => s.isDesigning);
  const progress = useAppStore((s) => s.progress);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const designResults = useAppStore((s) => s.designResults);

  const tmOkCount = designResults.filter((r) => r.tm_condition_met).length;

  return (
    <div className="flex items-center gap-2 px-4 py-1 bg-gray-100 border-t border-gray-300 text-xs text-gray-600">
      <span className="flex-1 truncate">{statusMessage}</span>
      {totalCount > 0 && (
        <span className="text-gray-500">
          {successCount}/{totalCount} designed | Tm OK: {tmOkCount}/
          {successCount}
        </span>
      )}
      {isDesigning && <Progress value={progress} className="w-32 h-2" />}
      {sidecarStatus === "error" && (
        <span className="inline-flex items-center gap-1 bg-red-600 text-white text-[10px] px-2 py-0.5 rounded whitespace-nowrap">
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
        className={`w-2 h-2 rounded-full flex-shrink-0 ${
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
