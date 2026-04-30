import { useEffect, useState } from "react";
import { useAppStore } from "../../../store/appStore";
import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult } from "../../../types/models";
import { validateSeq } from "../../../lib/validation";
import { ColoredFwdSeq, formatTolerance } from "../primerDisplay";
import { OffTargetDetail } from "./OffTargetDetail";

function CandidateRow({
  c, rowClass, label, actions, onOtClick, isFullOverlap,
}: {
  c: SdmPrimerResult;
  rowClass: string;
  label: React.ReactNode;
  actions: React.ReactNode;
  onOtClick: (c: SdmPrimerResult) => void;
  isFullOverlap: boolean;
}) {
  return (
    <tr className={`border-b border-border ${rowClass}`}>
      <td className="px-2 py-1 text-center">{label}</td>
      <td className="px-2 py-1 font-mono break-all max-w-40">
        <ColoredFwdSeq seq={c.forward_seq} overlapLen={c.overlap_len ?? 0} />
      </td>
      <td className="px-2 py-1 font-mono break-all max-w-36">{c.reverse_seq}</td>
      <td className="px-2 py-1 text-center">{c.fwd_len}</td>
      <td className="px-2 py-1 text-center">{c.rev_len}</td>
      <td className="px-2 py-1 text-center">{c.tm_no_fwd.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.tm_no_rev.toFixed(1)}</td>
      {!isFullOverlap && (
        <td className="px-2 py-1 text-center">{c.tm_overlap.toFixed(1)}</td>
      )}
      <td className="px-2 py-1 text-center">{c.gc_fwd.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{c.gc_rev.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">{formatTolerance(c.tolerance_fwd, c.tolerance_rev, c.tolerance_used)}</td>
      <td className="px-2 py-1 text-center" title={c.warnings?.length ? c.warnings.join("\n") : ""}>
        {c.penalty.toFixed(1)}
      </td>
      <td className={`px-2 py-1 text-center ${c.has_offtarget ? "cursor-pointer" : ""}`}
        onClick={c.has_offtarget ? () => onOtClick(c) : undefined}
      >
        {c.has_offtarget ? <span className="text-destructive font-medium">!!</span> : <span className="text-success">OK</span>}
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
  const [alternativesError, setAlternativesError] = useState<string | null>(null);
  const [otDetailCand, setOtDetailCand] = useState<SdmPrimerResult | null>(null);
  const focusTrapRef = useFocusTrap<HTMLDivElement>();
  const getAlternatives = useAppStore((s) => s.getAlternatives);
  const swapPrimer = useAppStore((s) => s.swapPrimer);
  const applyCustomPrimer = useAppStore((s) => s.applyCustomPrimer);
  const evaluateCustomPrimer = useAppStore((s) => s.evaluateCustomPrimer);
  const addCustomCandidate = useAppStore((s) => s.addCustomCandidate);
  const removeCustomCandidate = useAppStore((s) => s.removeCustomCandidate);
  const backendDesignStateSynced = useAppStore((s) => s.backendDesignStateSynced);
  const customCandidates = useAppStore((s) => s.customCandidates)[mutation] ?? [];
  const isFullOverlap = useAppStore((s) => s.overlapMode) === "full";

  useEffect(() => {
    setCustomOverlap("");
    setCustomCodon("");
    setCustomDownstream("");
    setCustomRev("");
    setSeqError(null);
    setAlternativesError(null);
    setEvaluating(false);
    setOtDetailCand(null);
  }, [mutation]);

  useEffect(() => {
    if (!backendDesignStateSynced) {
      setCandidates([current]);
      setAlternativesError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setAlternativesError(null);
    getAlternatives(mutation).then((c) => {
      setCandidates(c);
      setLoading(false);
    }).catch((err: unknown) => {
      setCandidates([current]);
      setAlternativesError(err instanceof Error ? err.message : String(err));
      setLoading(false);
    });
  }, [mutation, getAlternatives, current, backendDesignStateSynced]);

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
    try {
      const result = await evaluateCustomPrimer(
        mutation,
        fwdSeq,
        revSeq,
        fwdInput ? customOverlap.trim().length : (current.overlap_len ?? 18),
      );
      addCustomCandidate(mutation, result);
    } catch (err) {
      setSeqError(err instanceof Error ? err.message : String(err));
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
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div
        ref={focusTrapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="candidate-popover-title"
        className="max-h-[80vh] max-w-4xl overflow-auto rounded-container border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">Candidate Review</div>
            <h3 id="candidate-popover-title" className="mt-1 text-lg font-semibold text-foreground">
            {mutation} — {candidates?.length ?? "..."} candidates
            </h3>
          </div>
          <button
            onClick={onClose}
            className="px-2 text-lg text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {loading ? (
          <div className="text-xs text-muted-foreground py-4 text-center">Loading...</div>
        ) : !candidates || candidates.length === 0 ? (
          <div className="text-xs text-muted-foreground py-4 text-center">No candidates</div>
        ) : (
          <>
          {!backendDesignStateSynced && (
            <div className="mb-2 rounded bg-warning/10 px-2 py-1 text-caption text-warning">
              Backend alternatives are unavailable until you re-design this workspace. Manual primer evaluation still works.
            </div>
          )}
          {alternativesError && (
            <div className="mb-2 rounded bg-destructive/10 px-2 py-1 text-caption text-destructive">
              Failed to load alternatives: {alternativesError}
            </div>
          )}
          <div className="mb-2 text-caption text-muted-foreground">
            Ranked by penalty (lower = better). #1 is auto-selected as default.
          </div>
          <table className="w-full border-collapse text-caption">
            <thead>
              <tr className="bg-muted text-muted-foreground font-semibold">
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">Forward</th>
                <th className="px-2 py-1 text-left">Reverse</th>
                <th className="px-2 py-1">Fwd</th>
                <th className="px-2 py-1">Rev</th>
                <th className="px-2 py-1">Tm F</th>
                <th className="px-2 py-1">Tm R</th>
                {!isFullOverlap && <th className="px-2 py-1">Tm Ov</th>}
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
                  ? "bg-warning/10 font-semibold"
                  : isBest
                    ? "bg-success/10"
                    : "hover:bg-muted/50";
                return (
                  <CandidateRow key={idx} c={c} rowClass={rowClass} onOtClick={setOtDetailCand} isFullOverlap={isFullOverlap}
                    label={<>{idx + 1}{isBest && <span className="ml-0.5 text-success text-plate-tiny">best</span>}</>}
                    actions={
                      <div className="flex gap-0.5 justify-center items-center">
                        {isCurrent && <span className="text-warning text-plate-tiny mr-0.5">✓</span>}
                        <button
                          className="rounded px-1 py-0.5 text-plate-tiny text-foreground bg-foreground/10 hover:bg-foreground/20 disabled:opacity-40"
                          onClick={() => handleSwap(idx, "both")}
                          title={backendDesignStateSynced ? "Use both Fwd+Rev" : "Re-design to enable swapping"}
                          disabled={!backendDesignStateSynced}
                        >
                          Both
                        </button>
                        <button
                          className="rounded bg-success px-1 py-0.5 text-plate-tiny text-white hover:bg-success/80 disabled:opacity-40"
                          onClick={() => handleSwap(idx, "fwd")}
                          title={backendDesignStateSynced ? "Use Forward only" : "Re-design to enable swapping"}
                          disabled={!backendDesignStateSynced}
                        >
                          F
                        </button>
                        <button
                          className="rounded bg-warning px-1 py-0.5 text-plate-tiny text-white hover:bg-warning/80 disabled:opacity-40"
                          onClick={() => handleSwap(idx, "rev")}
                          title={backendDesignStateSynced ? "Use Reverse only" : "Re-design to enable swapping"}
                          disabled={!backendDesignStateSynced}
                        >
                          R
                        </button>
                      </div>
                    }
                  />
                );
              })}
              {customCandidates.map((c, ci) => (
                <CandidateRow key={`custom-${ci}`} c={c} rowClass="bg-primary/5" onOtClick={setOtDetailCand} isFullOverlap={isFullOverlap}
                  label={<span className="text-primary text-plate-tiny">C{ci + 1}</span>}
                  actions={
                    <div className="flex gap-0.5 justify-center">
                      <button className="rounded bg-primary px-1 py-0.5 text-plate-tiny text-primary-foreground hover:bg-primary/80" onClick={() => handleApplyCustom(c)} title="Apply this custom primer">Use</button>
                      <button className="rounded bg-muted-foreground/50 px-1 py-0.5 text-plate-tiny text-white hover:bg-muted-foreground" onClick={() => handleDeleteCustom(ci)} title="Remove">×</button>
                    </div>
                  }
                />
              ))}
            </tbody>
          </table>

          {/* Custom primer input */}
          <div className="mt-4 border-t border-border pt-4">
            <div className="mb-2 text-caption font-semibold uppercase tracking-widest text-muted-foreground">Custom Primer</div>
            <div className="space-y-1">
              <div className="flex items-center gap-0.5">
                <span className="text-plate-tiny text-muted-foreground w-6">Fwd:</span>
                <input
                  className="flex-1 text-caption font-mono border border-info/30 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-info"
                  style={{ color: "hsl(var(--info))" }}
                  placeholder="Overlap"
                  value={customOverlap}
                  onChange={(e) => setCustomOverlap(e.target.value.toUpperCase())}
                />
                <input
                  className="w-12 text-caption font-mono font-semibold border border-destructive/30 rounded px-1 py-1 text-center focus:outline-none focus:ring-1 focus:ring-destructive"
                  style={{ color: "hsl(var(--destructive))" }}
                  placeholder="Codon"
                  maxLength={3}
                  value={customCodon}
                  onChange={(e) => setCustomCodon(e.target.value.toUpperCase())}
                />
                <input
                  className="flex-1 text-caption font-mono border border-border rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-ring"
                  placeholder="Downstream"
                  value={customDownstream}
                  onChange={(e) => setCustomDownstream(e.target.value.toUpperCase())}
                />
              </div>
              <div className="flex items-center gap-0.5">
                <span className="text-plate-tiny text-muted-foreground w-6">Rev:</span>
                <input
                  className="flex-1 text-caption font-mono border border-warning/30 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-warning"
                  placeholder="Reverse sequence (5' → 3')"
                  value={customRev}
                  onChange={(e) => setCustomRev(e.target.value.toUpperCase())}
                />
                <button
                  className="rounded-full bg-primary px-3 py-1 text-caption text-primary-foreground hover:bg-primary/80 disabled:opacity-40"
                  disabled={(!(customOverlap + customCodon + customDownstream).trim() && !customRev.trim()) || evaluating}
                  onClick={handleEvaluate}
                >
                  {evaluating ? "..." : "Evaluate"}
                </button>
              </div>
            </div>
            {seqError && (
              <div className="mt-1 rounded-xl bg-destructive/10 px-2 py-1 text-caption text-destructive">{seqError}</div>
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
