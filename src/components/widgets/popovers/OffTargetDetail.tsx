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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div aria-hidden="true" className="fixed inset-0" />
      <div
        ref={focusTrapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="offtarget-detail-title"
        className="bg-white rounded-lg shadow-xl p-4 min-w-[360px] max-w-lg max-h-[60vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 id="offtarget-detail-title" className="text-sm font-semibold">
            {result.mutation} — Off-Target Sites ({allHits.length})
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {allHits.length === 0 ? (
          <div className="text-xs text-gray-400 py-4 text-center">No off-target hits</div>
        ) : (
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50 text-gray-600 font-semibold">
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
                <tr key={i} className="border-b border-gray-100">
                  <td className={`px-2 py-1.5 font-medium ${h.primer === "Fwd" ? "text-blue-600" : "text-orange-600"}`}>
                    {h.primer}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.position}</td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={`inline-block px-1 py-0.5 rounded text-[9px] ${h.strand === "sense" ? "bg-blue-50 text-blue-700" : "bg-purple-50 text-purple-700"}`}>
                      {h.strand === "sense" ? "+" : "−"}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.match_length}</td>
                  <td className="px-2 py-1.5 text-right font-mono">{h.tm.toFixed(1)}</td>
                  <td className="px-2 py-1.5 font-mono text-[10px] break-all max-w-[140px]">{h.match_seq}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
