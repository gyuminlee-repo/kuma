import { useEffect, useState } from "react";
import { useAppStore } from "../../../store/appStore";
import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult, FailedMutation } from "../../../types/models";
import { validateSeq } from "../../../lib/validation";

export function FailedMutationPopover({
  failed,
  onClose,
}: {
  failed: FailedMutation;
  onClose: () => void;
}) {
  const storeTmFwd = useAppStore((s) => s.tmFwdTarget);
  const storeTmRev = useAppStore((s) => s.tmRevTarget);
  const storeTmOv = useAppStore((s) => s.tmOverlapTarget);
  const storeGcMin = useAppStore((s) => s.gcMin);
  const storeGcMax = useAppStore((s) => s.gcMax);
  const storeFwdMin = useAppStore((s) => s.fwdLenMin);
  const storeFwdMax = useAppStore((s) => s.fwdLenMax);
  const storeRevMin = useAppStore((s) => s.revLenMin);
  const storeRevMax = useAppStore((s) => s.revLenMax);
  const storeCodon = useAppStore((s) => s.codonStrategy);

  const [tmFwd, setTmFwd] = useState(String(storeTmFwd));
  const [tmRev, setTmRev] = useState(String(storeTmRev));
  const [tmOv, setTmOv] = useState(String(storeTmOv));
  const [gcMin, setGcMin] = useState(String(storeGcMin));
  const [gcMax, setGcMax] = useState(String(storeGcMax));
  const [fwdMin, setFwdMin] = useState(String(storeFwdMin));
  const [fwdMax, setFwdMax] = useState(String(storeFwdMax));
  const [revMin, setRevMin] = useState(String(storeRevMin));
  const [revMax, setRevMax] = useState(String(storeRevMax));
  const [tolMax, setTolMax] = useState("5.0");
  const [retrying, setRetrying] = useState(false);
  const [candidates, setCandidates] = useState<SdmPrimerResult[]>([]);
  const [retryError, setRetryError] = useState<string | null>(null);

  const [customOverlap, setCustomOverlap] = useState("");
  const [customCodon, setCustomCodon] = useState("");
  const [customDownstream, setCustomDownstream] = useState("");
  const [customRev, setCustomRev] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [seqError, setSeqError] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);

  const focusTrapRef = useFocusTrap<HTMLDivElement>();
  const retryFailedMutation = useAppStore((s) => s.retryFailedMutation);
  const evaluateCustomPrimer = useAppStore((s) => s.evaluateCustomPrimer);
  const addDesignResult = useAppStore((s) => s.addDesignResult);

  useEffect(() => {
    setTmFwd(String(storeTmFwd));
    setTmRev(String(storeTmRev));
    setTmOv(String(storeTmOv));
    setGcMin(String(storeGcMin));
    setGcMax(String(storeGcMax));
    setFwdMin(String(storeFwdMin));
    setFwdMax(String(storeFwdMax));
    setRevMin(String(storeRevMin));
    setRevMax(String(storeRevMax));
    setTolMax("5.0");
    setRetrying(false);
    setCandidates([]);
    setRetryError(null);
    setCustomOverlap("");
    setCustomCodon("");
    setCustomDownstream("");
    setCustomRev("");
    setEvaluating(false);
    setSeqError(null);
    setShowManual(false);
  }, [
    failed.mutation,
    storeFwdMax,
    storeFwdMin,
    storeGcMax,
    storeGcMin,
    storeRevMax,
    storeRevMin,
    storeTmFwd,
    storeTmOv,
    storeTmRev,
  ]);

  async function handleRetry() {
    setRetrying(true);
    setRetryError(null);
    setCandidates([]);
    try {
      const results = await retryFailedMutation(failed.mutation, {
        tm_fwd_target: parseFloat(tmFwd),
        tm_rev_target: parseFloat(tmRev),
        tm_overlap_target: parseFloat(tmOv),
        gc_min: parseFloat(gcMin),
        gc_max: parseFloat(gcMax),
        fwd_len_min: parseInt(fwdMin),
        fwd_len_max: parseInt(fwdMax),
        rev_len_min: parseInt(revMin),
        rev_len_max: parseInt(revMax),
        tol_max: parseFloat(tolMax),
        codon_strategy: storeCodon,
      });
      if (results.length === 0) {
        setRetryError("No candidates found with these parameters");
      } else {
        setCandidates(results);
      }
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : String(err));
    }
    setRetrying(false);
  }

  function handleSelect(candidate: SdmPrimerResult) {
    addDesignResult(failed.mutation, candidate);
    onClose();
  }

  async function handleEvaluate() {
    const fwdSeq = (customOverlap + customCodon + customDownstream).trim();
    const revSeq = customRev.trim();
    if (!fwdSeq || !revSeq) return;
    const fwdErr = validateSeq(fwdSeq);
    const revErr = validateSeq(revSeq);
    if (fwdErr || revErr) {
      setSeqError(`Invalid sequence: ${fwdErr || revErr}`);
      return;
    }
    setSeqError(null);
    setEvaluating(true);
    try {
      const result = await evaluateCustomPrimer(
        failed.mutation,
        fwdSeq,
        revSeq,
        customOverlap.trim().length,
      );
      addDesignResult(failed.mutation, result);
      onClose();
    } catch (err) {
      setSeqError(err instanceof Error ? err.message : String(err));
    }
    setEvaluating(false);
  }

  const inp = "w-14 h-5 text-[10px] border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div aria-hidden="true" className="fixed inset-0" />
      <div ref={focusTrapRef} role="dialog" aria-modal="true" aria-labelledby="failed-mutation-title" className="bg-white rounded-lg shadow-xl p-4 min-w-[440px] max-w-xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-3">
          <h3 id="failed-mutation-title" className="text-sm font-semibold text-red-700">{failed.mutation} — Design Failed</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg px-2" aria-label="Close">×</button>
        </div>

        <div className="bg-red-50 rounded px-3 py-2 mb-3 text-xs text-red-700">
          <span className="font-semibold">Reason:</span> {failed.reason}
        </div>

        {/* Retry with parameters */}
        <div className="text-[9px] uppercase text-gray-400 tracking-wider mb-1">Retry with parameters</div>
        <div className="bg-gray-50 rounded p-2 space-y-1 mb-2">
          <div className="flex items-center gap-1 text-[10px]">
            <span className="w-10 text-gray-500">Tm:</span>
            <span className="text-gray-400">F</span><input className={inp} value={tmFwd} onChange={(e) => setTmFwd(e.target.value)} />
            <span className="text-gray-400">R</span><input className={inp} value={tmRev} onChange={(e) => setTmRev(e.target.value)} />
            <span className="text-gray-400">Ov</span><input className={inp} value={tmOv} onChange={(e) => setTmOv(e.target.value)} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-1 text-[10px]">
            <span className="w-10 text-gray-500">GC%:</span>
            <input className={inp} value={gcMin} onChange={(e) => setGcMin(e.target.value)} />
            <span className="text-gray-400">~</span>
            <input className={inp} value={gcMax} onChange={(e) => setGcMax(e.target.value)} />
            <span className="text-gray-400 ml-2">Tol max</span>
            <input className={inp} value={tolMax} onChange={(e) => setTolMax(e.target.value)} />
            <span className="text-gray-400">°C</span>
          </div>
          <div className="flex items-center gap-1 text-[10px]">
            <span className="w-10 text-gray-500">Length:</span>
            <span className="text-gray-400">F</span><input className={inp} value={fwdMin} onChange={(e) => setFwdMin(e.target.value)} />
            <span className="text-gray-400">~</span><input className={inp} value={fwdMax} onChange={(e) => setFwdMax(e.target.value)} />
            <span className="text-gray-400 ml-1">R</span><input className={inp} value={revMin} onChange={(e) => setRevMin(e.target.value)} />
            <span className="text-gray-400">~</span><input className={inp} value={revMax} onChange={(e) => setRevMax(e.target.value)} />
            <span className="text-gray-400">bp</span>
          </div>
          <button
            className="mt-1 px-4 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700 disabled:opacity-40"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? "Designing..." : "Retry"}
          </button>
        </div>

        {retryError && (
          <div className="text-[10px] text-amber-700 bg-amber-50 rounded px-2 py-1 mb-2">{retryError}</div>
        )}

        {/* Candidate list */}
        {candidates.length > 0 && (
          <div className="mb-3">
            <div className="text-[9px] uppercase text-gray-400 tracking-wider mb-1">Candidates ({candidates.length})</div>
            <div className="max-h-40 overflow-y-auto border border-gray-200 rounded">
              <table className="w-full text-[10px]">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-1 py-0.5 text-left">Fwd</th>
                    <th className="px-1 py-0.5 text-left">Rev</th>
                    <th className="px-1 py-0.5">Tm F</th>
                    <th className="px-1 py-0.5">Tm R</th>
                    <th className="px-1 py-0.5">Pen</th>
                    <th className="px-1 py-0.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c, i) => (
                    <tr key={i} className="border-t border-gray-100 hover:bg-green-50">
                      <td className="px-1 py-0.5 font-mono truncate max-w-[120px]" title={c.forward_seq}>{c.forward_seq.slice(0, 15)}...</td>
                      <td className="px-1 py-0.5 font-mono truncate max-w-[100px]" title={c.reverse_seq}>{c.reverse_seq.slice(0, 12)}...</td>
                      <td className="px-1 py-0.5 text-center">{c.tm_no_fwd.toFixed(1)}</td>
                      <td className="px-1 py-0.5 text-center">{c.tm_no_rev.toFixed(1)}</td>
                      <td className="px-1 py-0.5 text-center">{c.penalty.toFixed(1)}</td>
                      <td className="px-1 py-0.5">
                        <button
                          className="px-2 py-0.5 bg-green-500 text-white rounded text-[9px] hover:bg-green-600"
                          onClick={() => handleSelect(c)}
                        >
                          Select
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Manual input (collapsible) */}
        <button
          className="text-[10px] text-gray-400 hover:text-gray-600 underline mb-1"
          onClick={() => setShowManual(!showManual)}
        >
          {showManual ? "Hide manual input" : "Or enter manually..."}
        </button>
        {showManual && (
          <div className="space-y-1">
            <div className="flex items-center gap-0.5">
              <span className="text-[9px] text-gray-400 w-6">Fwd:</span>
              <input className="flex-1 text-[10px] font-mono border border-blue-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400" style={{ color: "#3b82f6" }} placeholder="Overlap" value={customOverlap} onChange={(e) => setCustomOverlap(e.target.value.toUpperCase())} />
              <input className="w-12 text-[10px] font-mono font-semibold border border-red-300 rounded px-1 py-1 text-center focus:outline-none focus:ring-1 focus:ring-red-400" style={{ color: "#ef4444" }} placeholder="Codon" maxLength={3} value={customCodon} onChange={(e) => setCustomCodon(e.target.value.toUpperCase())} />
              <input className="flex-1 text-[10px] font-mono border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-gray-400" placeholder="Downstream" value={customDownstream} onChange={(e) => setCustomDownstream(e.target.value.toUpperCase())} />
            </div>
            <div className="flex items-center gap-0.5">
              <span className="text-[9px] text-gray-400 w-6">Rev:</span>
              <input className="flex-1 text-[10px] font-mono border border-orange-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-orange-400" placeholder="Reverse sequence (5' → 3')" value={customRev} onChange={(e) => setCustomRev(e.target.value.toUpperCase())} />
              <button className="px-3 py-1 bg-purple-500 text-white rounded text-[10px] hover:bg-purple-600 disabled:opacity-40" disabled={!(customOverlap + customCodon + customDownstream).trim() || !customRev.trim() || evaluating} onClick={handleEvaluate}>
                {evaluating ? "..." : "Evaluate"}
              </button>
            </div>
            {seqError && <div className="text-[10px] text-red-600 bg-red-50 rounded px-2 py-1 mt-1">{seqError}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
