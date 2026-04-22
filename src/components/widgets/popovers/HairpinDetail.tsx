import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult } from "../../../types/models";

export function HairpinDetail({
  result,
  onClose,
}: {
  result: SdmPrimerResult;
  onClose: () => void;
}) {
  const focusTrapRef = useFocusTrap<HTMLDivElement>();

  const rows = [
    { label: "Hairpin Fwd", tm: result.hairpin_tm_fwd ?? 0, dg: result.hairpin_dg_fwd ?? 0 },
    { label: "Hairpin Rev", tm: result.hairpin_tm_rev ?? 0, dg: result.hairpin_dg_rev ?? 0 },
    { label: "Homodimer Fwd", tm: result.homodimer_tm_fwd ?? 0, dg: result.homodimer_dg_fwd ?? 0 },
    { label: "Homodimer Rev", tm: result.homodimer_tm_rev ?? 0, dg: result.homodimer_dg_rev ?? 0 },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div aria-hidden="true" className="fixed inset-0" />
      <div
        ref={focusTrapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="hairpin-detail-title"
        className="min-w-[320px] rounded-[24px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,251,243,0.98),rgba(248,251,255,0.98))] p-5 shadow-[0_32px_90px_rgba(15,23,42,0.28)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="hairpin-detail-title" className="text-lg font-semibold text-slate-900">
            {result.mutation} — Secondary Structure
          </h3>
          <button
            onClick={onClose}
            className="px-2 text-lg text-slate-400 hover:text-slate-600"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50 text-slate-600 font-semibold">
              <th className="px-3 py-1.5 text-left">Type</th>
              <th className="px-3 py-1.5 text-right">Tm (°C)</th>
              <th className="px-3 py-1.5 text-right">dG (kcal/mol)</th>
              <th className="px-3 py-1.5 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-b border-slate-100">
                <td className="px-3 py-1.5">{r.label}</td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.tm > 0 ? r.tm.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.dg !== 0 ? r.dg.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-center">
                  {r.tm <= 0 ? (
                    <span className="text-slate-400">—</span>
                  ) : r.tm > 40 ? (
                    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-yellow-100 text-yellow-800">
                      warn
                    </span>
                  ) : (
                    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">
                      OK
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {result.warnings.length > 0 && (
          <div className="mt-3 space-y-0.5 text-[10px] text-slate-400">
            <div className="font-semibold text-slate-600">Warnings:</div>
            {result.warnings.map((w, i) => (
              <div key={i} className="text-yellow-700">{w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
