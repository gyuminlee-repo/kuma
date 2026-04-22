import { useAppStore } from "../../store/appStore";

export function StatusBar({ sidecarStatus, onRetry }: { sidecarStatus: string; onRetry: () => void }) {
  const statusMessage = useAppStore((s) => s.statusMessage);

  return (
    <div className="h-6 flex items-center gap-2 border-t border-zinc-900/10 bg-[linear-gradient(180deg,rgba(247,244,239,0.96),rgba(239,236,231,0.96))] px-3 text-xs text-zinc-600">
      <span className="flex-1 truncate">{statusMessage}</span>
      {sidecarStatus === "error" && (
        <span className="inline-flex items-center gap-1 text-destructive whitespace-nowrap">
          Sidecar failed.
          <button
            className="underline font-medium hover:opacity-70"
            onClick={onRetry}
          >
            Retry
          </button>
        </span>
      )}
      <span
        className={`h-2 w-2 rounded-full flex-shrink-0 ${
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
