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

  const inp = "h-6 w-14 rounded-lg border border-border bg-card px-1 text-center text-caption focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-[2px]" onClick={onClose} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div aria-hidden="true" className="fixed inset-0" />
      <div ref={focusTrapRef} role="dialog" aria-modal="true" aria-labelledby="failed-mutation-title" className="min-w-[520px] max-h-[80vh] max-w-2xl overflow-y-auto rounded-container border border-border bg-card p-5 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-caption font-semibold uppercase tracking-widest text-destructive">Failure Recovery</div>
            <h3 id="failed-mutation-title" className="mt-1 text-lg font-semibold text-foreground">{failed.mutation} — Design Failed</h3>
          </div>
          <button onClick={onClose} className="px-2 text-lg text-muted-foreground hover:text-foreground" aria-label="Close">×</button>
        </div>

        <div className="mb-4 rounded-2xl border border-destructive/20 bg-destructive/10 px-3 py-3 text-xs text-destructive">
          <span className="font-semibold">Reason:</span> {failed.reason}
        </div>

        {/* Retry with parameters */}
        <div className="mb-1 text-caption font-semibold uppercase tracking-widest text-muted-foreground">Retry with parameters</div>
        <div className="mb-3 space-y-2 rounded-2xl border border-border bg-card p-3">
          <div className="flex items-center gap-1 text-caption">
            <span className="w-10 text-muted-foreground">Tm:</span>
            <span className="text-muted-foreground">F</span><input className={inp} value={tmFwd} onChange={(e) => setTmFwd(e.target.value)} />
            <span className="text-muted-foreground">R</span><input className={inp} value={tmRev} onChange={(e) => setTmRev(e.target.value)} />
            <span className="text-muted-foreground">Ov</span><input className={inp} value={tmOv} onChange={(e) => setTmOv(e.target.value)} />
            <span className="text-muted-foreground">°C</span>
          </div>
          <div className="flex items-center gap-1 text-caption">
            <span className="w-10 text-muted-foreground">GC%:</span>
            <input className={inp} value={gcMin} onChange={(e) => setGcMin(e.target.value)} />
            <span className="text-muted-foreground">~</span>
            <input className={inp} value={gcMax} onChange={(e) => setGcMax(e.target.value)} />
            <span className="ml-2 text-muted-foreground">Tol max</span>
            <input className={inp} value={tolMax} onChange={(e) => setTolMax(e.target.value)} />
            <span className="text-muted-foreground">°C</span>
          </div>
          <div className="flex items-center gap-1 text-caption">
            <span className="w-10 text-muted-foreground">Length:</span>
            <span className="text-muted-foreground">F</span><input className={inp} value={fwdMin} onChange={(e) => setFwdMin(e.target.value)} />
            <span className="text-muted-foreground">~</span><input className={inp} value={fwdMax} onChange={(e) => setFwdMax(e.target.value)} />
            <span className="ml-1 text-muted-foreground">R</span><input className={inp} value={revMin} onChange={(e) => setRevMin(e.target.value)} />
            <span className="text-muted-foreground">~</span><input className={inp} value={revMax} onChange={(e) => setRevMax(e.target.value)} />
            <span className="text-muted-foreground">bp</span>
          </div>
          <button
            className="mt-1 rounded-full bg-foreground px-4 py-1.5 text-xs text-background hover:bg-foreground/80 disabled:opacity-40"
            onClick={handleRetry}
            disabled={retrying}
          >
            {retrying ? "Designing..." : "Retry"}
          </button>
        </div>

        {retryError && (
          <div className="text-caption text-warning bg-warning/10 rounded px-2 py-1 mb-2">{retryError}</div>
        )}

        {/* Candidate list */}
        {candidates.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 text-caption font-semibold uppercase tracking-widest text-muted-foreground">Candidates ({candidates.length})</div>
            <div className="max-h-40 overflow-y-auto rounded-2xl border border-border">
              <table className="w-full text-caption">
                <thead className="sticky top-0 bg-muted">
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
                    <tr key={i} className="border-t border-border hover:bg-success/5">
                      <td className="px-1 py-0.5 font-mono truncate max-w-28" title={c.forward_seq}>{c.forward_seq.slice(0, 15)}...</td>
                      <td className="px-1 py-0.5 font-mono truncate max-w-24" title={c.reverse_seq}>{c.reverse_seq.slice(0, 12)}...</td>
                      <td className="px-1 py-0.5 text-center">{c.tm_no_fwd.toFixed(1)}</td>
                      <td className="px-1 py-0.5 text-center">{c.tm_no_rev.toFixed(1)}</td>
                      <td className="px-1 py-0.5 text-center">{c.penalty.toFixed(1)}</td>
                      <td className="px-1 py-0.5">
                        <button
                          className="rounded-full bg-success px-2 py-0.5 text-plate-tiny text-white hover:bg-success/80"
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
          className="mb-1 text-caption text-muted-foreground underline hover:text-foreground"
          onClick={() => setShowManual(!showManual)}
        >
          {showManual ? "Hide manual input" : "Or enter manually..."}
        </button>
        {showManual && (
          <div className="space-y-1">
            <div className="flex items-center gap-0.5">
              <span className="w-6 text-plate-tiny text-muted-foreground">Fwd:</span>
              <input className="flex-1 text-caption font-mono border border-info/30 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-info" style={{ color: "hsl(var(--info))" }} placeholder="Overlap" value={customOverlap} onChange={(e) => setCustomOverlap(e.target.value.toUpperCase())} />
              <input className="w-12 text-caption font-mono font-semibold border border-destructive/30 rounded px-1 py-1 text-center focus:outline-none focus:ring-1 focus:ring-destructive" style={{ color: "hsl(var(--destructive))" }} placeholder="Codon" maxLength={3} value={customCodon} onChange={(e) => setCustomCodon(e.target.value.toUpperCase())} />
              <input className="flex-1 text-caption font-mono border border-border rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-ring" placeholder="Downstream" value={customDownstream} onChange={(e) => setCustomDownstream(e.target.value.toUpperCase())} />
            </div>
            <div className="flex items-center gap-0.5">
              <span className="w-6 text-plate-tiny text-muted-foreground">Rev:</span>
              <input className="flex-1 text-caption font-mono border border-warning/30 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-warning" placeholder="Reverse sequence (5' → 3')" value={customRev} onChange={(e) => setCustomRev(e.target.value.toUpperCase())} />
              <button className="rounded-full bg-primary px-3 py-1 text-caption text-primary-foreground hover:bg-primary/80 disabled:opacity-40" disabled={!(customOverlap + customCodon + customDownstream).trim() || !customRev.trim() || evaluating} onClick={handleEvaluate}>
                {evaluating ? "..." : "Evaluate"}
              </button>
            </div>
            {seqError && <div className="text-caption text-destructive bg-destructive/10 rounded px-2 py-1 mt-1">{seqError}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
