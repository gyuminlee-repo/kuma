import { useEffect, useState } from "react";
import { useAppStore } from "../../../store/appStore";
import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult } from "../../../types/models";
import { validateSeq } from "../../../lib/validation";
import { ColoredFwdSeq, formatTolerance } from "../primerDisplay";
import { OffTargetDetail } from "./OffTargetDetail";

function CandidateRow({
  c, rowClass, label, actions, onOtClick,
}: {
  c: SdmPrimerResult;
  rowClass: string;
  label: React.ReactNode;
  actions: React.ReactNode;
  onOtClick: (c: SdmPrimerResult) => void;
}) {
  return (
    <tr className={`border-b border-gray-100 ${rowClass}`}>
      <td className="px-2 py-1 text-center">{label}</td>
      <td className="px-2 py-1 font-mono break-all max-w-[160px]">
        <ColoredFwdSeq seq={c.forward_seq} overlapLen={c.overlap_len ?? 0} />
      </td>
      <td className="px-2 py-1 font-mono break-all max-w-[140px]">{c.reverse_seq}</td>
      <td className="px-2 py-1 text-center">{c.fwd_len}</td>
      <td className="px-2 py-1 text-center">{c.rev_len}</td>
      <td className="px-2 py-1 text-center">{c.tm_no_fwd.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.tm_no_rev.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.tm_overlap.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.gc_fwd.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.gc_rev.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{formatTolerance(c.tolerance_fwd, c.tolerance_rev, c.tolerance_used)}</td>
      <td className="px-2 py-1 text-center" title={c.warnings?.length ? c.warnings.join("\n") : ""}>
        {c.penalty.toFixed(1)}
      </td>
      <td className={`px-2 py-1 text-center ${c.has_offtarget ? "cursor-pointer" : ""}`}
        onClick={c.has_offtarget ? () => onOtClick(c) : undefined}
      >
        {c.has_offtarget ? <span className="text-red-600 font-medium">!!</span> : <span className="text-green-600">OK</span>}
      </td>
      <td className="px-2 py-1 text-center whitespace-nowrap">{actions}</td>
    </tr>
  );
}

export function CandidatePopover({
  mutation,
  current,
  onClose,
}: {
  mutation: string;
  current: SdmPrimerResult;
  onClose: () => void;
}) {
  const [candidates, setCandidates] = useState<SdmPrimerResult[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [customOverlap, setCustomOverlap] = useState("");
  const [customCodon, setCustomCodon] = useState("");
  const [customDownstream, setCustomDownstream] = useState("");
  const [customRev, setCustomRev] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [seqError, setSeqError] = useState<string | null>(null);
  const [otDetailCand, setOtDetailCand] = useState<SdmPrimerResult | null>(null);
  const focusTrapRef = useFocusTrap<HTMLDivElement>();
  const getAlternatives = useAppStore((s) => s.getAlternatives);
  const swapPrimer = useAppStore((s) => s.swapPrimer);
  const applyCustomPrimer = useAppStore((s) => s.applyCustomPrimer);
  const evaluateCustomPrimer = useAppStore((s) => s.evaluateCustomPrimer);
  const addCustomCandidate = useAppStore((s) => s.addCustomCandidate);
  const removeCustomCandidate = useAppStore((s) => s.removeCustomCandidate);
  const customCandidates = useAppStore((s) => s.customCandidates)[mutation] ?? [];

  useEffect(() => {
    getAlternatives(mutation).then((c) => {
      setCandidates(c);
      setLoading(false);
    }).catch(() => {
      setCandidates([current]);
      setLoading(false);
    });
  }, [mutation, getAlternatives, current]);

  async function handleEvaluate() {
    const fwdInput = (customOverlap + customCodon + customDownstream).trim();
    const revInput = customRev.trim();
    if (!fwdInput && !revInput) return;
    const fwdSeq = fwdInput || current.forward_seq;
    const revSeq = revInput || current.reverse_seq;
    const fwdErr = validateSeq(fwdInput);
    const revErr = validateSeq(revInput);
    if (fwdErr || revErr) {
      setSeqError(`Invalid sequence: ${fwdErr || revErr}`);
      return;
    }
    setSeqError(null);
    const isDup = customCandidates.some((c) => c.forward_seq === fwdSeq && c.reverse_seq === revSeq);
    if (isDup) {
      setSeqError("Duplicate custom primer — already added");
      return;
    }
    setEvaluating(true);
    const result = await evaluateCustomPrimer(mutation, fwdSeq, revSeq, fwdInput ? customOverlap.trim().length : (current.overlap_len ?? 18));
    if (result) {
      addCustomCandidate(mutation, result);
    }
    setEvaluating(false);
  }

  async function handleSwap(idx: number, type: "both" | "fwd" | "rev" = "both") {
    await swapPrimer(mutation, idx, type);
    if (type === "both") onClose();
  }

  function handleApplyCustom(result: SdmPrimerResult) {
    applyCustomPrimer(mutation, result);
    onClose();
  }

  function handleDeleteCustom(ci: number) {
    removeCustomCandidate(mutation, ci);
  }

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
        aria-labelledby="candidate-popover-title"
        className="bg-white rounded-lg shadow-xl p-4 max-w-3xl max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 id="candidate-popover-title" className="text-sm font-semibold">
            {mutation} — {candidates?.length ?? "..."} candidates
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {loading ? (
          <div className="text-xs text-gray-400 py-4 text-center">Loading...</div>
        ) : !candidates || candidates.length === 0 ? (
          <div className="text-xs text-gray-400 py-4 text-center">No candidates</div>
        ) : (
          <>
          <div className="text-[10px] text-gray-500 mb-2">
            Ranked by penalty (lower = better). #1 is auto-selected as default.
          </div>
          <table className="w-full text-[10px] border-collapse">
            <thead>
              <tr className="bg-gray-50 text-gray-600 font-semibold">
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">Forward</th>
                <th className="px-2 py-1 text-left">Reverse</th>
                <th className="px-2 py-1">Fwd</th>
                <th className="px-2 py-1">Rev</th>
                <th className="px-2 py-1">Tm F</th>
                <th className="px-2 py-1">Tm R</th>
                <th className="px-2 py-1">Tm Ov</th>
                <th className="px-2 py-1">GC% F</th>
                <th className="px-2 py-1">GC% R</th>
                <th className="px-2 py-1">Tol</th>
                <th className="px-2 py-1" title="Penalty = Tm deviation + GC deviation + codon changes + hairpin/homodimer">Pen</th>
                <th className="px-2 py-1">OT</th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, idx) => {
                const isCurrent = c.forward_seq === current.forward_seq
                  && c.reverse_seq === current.reverse_seq;
                const isBest = idx === 0;
                const rowClass = isCurrent
                  ? "bg-amber-50 font-semibold"
                  : isBest
                    ? "bg-green-50"
                    : "hover:bg-gray-50";
                return (
                  <CandidateRow key={idx} c={c} rowClass={rowClass} onOtClick={setOtDetailCand}
                    label={<>{idx + 1}{isBest && <span className="ml-0.5 text-green-600 text-[8px]">best</span>}</>}
                    actions={
                      <div className="flex gap-0.5 justify-center items-center">
                        {isCurrent && <span className="text-amber-600 text-[9px] mr-0.5">✓</span>}
                        <button className="px-1 py-0.5 bg-blue-500 text-white rounded text-[8px] hover:bg-blue-600" onClick={() => handleSwap(idx, "both")} title="Use both Fwd+Rev">Both</button>
                        <button className="px-1 py-0.5 bg-green-500 text-white rounded text-[8px] hover:bg-green-600" onClick={() => handleSwap(idx, "fwd")} title="Use Forward only">F</button>
                        <button className="px-1 py-0.5 bg-orange-500 text-white rounded text-[8px] hover:bg-orange-600" onClick={() => handleSwap(idx, "rev")} title="Use Reverse only">R</button>
                      </div>
                    }
                  />
                );
              })}
              {customCandidates.map((c, ci) => (
                <CandidateRow key={`custom-${ci}`} c={c} rowClass="bg-purple-50" onOtClick={setOtDetailCand}
                  label={<span className="text-purple-600 text-[9px]">C{ci + 1}</span>}
                  actions={
                    <div className="flex gap-0.5 justify-center">
                      <button className="px-1 py-0.5 bg-purple-500 text-white rounded text-[8px] hover:bg-purple-600" onClick={() => handleApplyCustom(c)} title="Apply this custom primer">Use</button>
                      <button className="px-1 py-0.5 bg-gray-400 text-white rounded text-[8px] hover:bg-gray-500" onClick={() => handleDeleteCustom(ci)} title="Remove">×</button>
                    </div>
                  }
                />
              ))}
            </tbody>
          </table>

          {/* Custom primer input */}
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="text-[10px] font-semibold text-gray-600 mb-1">Custom primer</div>
            <div className="space-y-1">
              <div className="flex items-center gap-0.5">
                <span className="text-[9px] text-gray-400 w-6">Fwd:</span>
                <input
                  className="flex-1 text-[10px] font-mono border border-blue-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                  style={{ color: "#3b82f6" }}
                  placeholder="Overlap"
                  value={customOverlap}
                  onChange={(e) => setCustomOverlap(e.target.value.toUpperCase())}
                />
                <input
                  className="w-12 text-[10px] font-mono font-semibold border border-red-300 rounded px-1 py-1 text-center focus:outline-none focus:ring-1 focus:ring-red-400"
                  style={{ color: "#ef4444" }}
                  placeholder="Codon"
                  maxLength={3}
                  value={customCodon}
                  onChange={(e) => setCustomCodon(e.target.value.toUpperCase())}
                />
                <input
                  className="flex-1 text-[10px] font-mono border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-gray-400"
                  placeholder="Downstream"
                  value={customDownstream}
                  onChange={(e) => setCustomDownstream(e.target.value.toUpperCase())}
                />
              </div>
              <div className="flex items-center gap-0.5">
                <span className="text-[9px] text-gray-400 w-6">Rev:</span>
                <input
                  className="flex-1 text-[10px] font-mono border border-orange-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-orange-400"
                  placeholder="Reverse sequence (5' → 3')"
                  value={customRev}
                  onChange={(e) => setCustomRev(e.target.value.toUpperCase())}
                />
                <button
                  className="px-3 py-1 bg-purple-500 text-white rounded text-[10px] hover:bg-purple-600 disabled:opacity-40"
                  disabled={(!(customOverlap + customCodon + customDownstream).trim() && !customRev.trim()) || evaluating}
                  onClick={handleEvaluate}
                >
                  {evaluating ? "..." : "Evaluate"}
                </button>
              </div>
            </div>
            {seqError && (
              <div className="text-[10px] text-red-600 bg-red-50 rounded px-2 py-1 mt-1">{seqError}</div>
            )}
          </div>
          </>
        )}

        {otDetailCand && (
          <OffTargetDetail
            result={otDetailCand}
            onClose={() => setOtDetailCand(null)}
          />
        )}
      </div>
    </div>
  );
}
