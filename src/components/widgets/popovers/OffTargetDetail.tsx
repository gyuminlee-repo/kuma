import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult } from "../../../types/models";

type PrimerLabel = "Fwd" | "Rev";

function withPrimer<T>(hits: T[], primer: PrimerLabel): Array<T & { primer: PrimerLabel }> {
  return hits.map((hit) => ({ ...hit, primer }));
}

export function OffTargetDetail({
  result,
  onClose,
}: {
  result: SdmPrimerResult;
  onClose: () => void;
}) {
  const focusTrapRef = useFocusTrap<HTMLDivElement>();

  const fwdHits = result.offtarget_fwd ?? [];
  const revHits = result.offtarget_rev ?? [];
  const allHits = [
    ...withPrimer(fwdHits, "Fwd"),
    ...withPrimer(revHits, "Rev"),
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div aria-hidden="true" className="fixed inset-0" />
      <div
        ref={focusTrapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="offtarget-detail-title"
        className="max-h-[60vh] min-w-popover max-w-2xl overflow-auto rounded-container border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="offtarget-detail-title" className="text-lg font-semibold text-foreground">
            {result.mutation} — Off-Target Sites ({allHits.length})
          </h3>
          <button
            onClick={onClose}
            className="px-2 text-lg text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {allHits.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">No off-target hits</div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-muted text-muted-foreground font-semibold">
                <th className="px-2 py-1.5 text-left">Primer</th>
                <th className="px-2 py-1.5 text-right">Position</th>
                <th className="px-2 py-1.5 text-center">Strand</th>
                <th className="px-2 py-1.5 text-right">Match (bp)</th>
                <th className="px-2 py-1.5 text-right">Tm (°C)</th>
                <th className="px-2 py-1.5 text-left">Sequence</th>
              </tr>
            </thead>
            <tbody>
              {allHits.map((h, i) => (
                <tr key={i} className="border-b border-border">
                  <td className={`px-2 py-1.5 font-medium ${h.primer === "Fwd" ? "text-info" : "text-warning"}`}>
                    {h.primer}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.position}</td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={`inline-block px-1 py-0.5 rounded text-plate-tiny ${h.strand === "sense" ? "bg-info/10 text-info" : "bg-primary/10 text-primary"}`}>
                      {h.strand === "sense" ? "+" : "−"}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.match_length}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.tm.toFixed(1)}</td>
                  <td className="px-2 py-1.5 font-mono text-caption break-all max-w-36">{h.match_seq}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
