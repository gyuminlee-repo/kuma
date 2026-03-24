import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult, FailedMutation } from "../../types/models";

const col = createColumnHelper<SdmPrimerResult & { rank: number }>();

const VALID_BASES = /^[ATGCatgc]*$/;
function validateSeq(seq: string): string | null {
  if (!seq) return null;
  if (!VALID_BASES.test(seq)) {
    const invalid = seq.replace(/[ATGCatgc]/g, "");
    return `Invalid characters: ${[...new Set(invalid)].join(", ")}`;
  }
  return null;
}

function formatTolerance(tf?: number, tr?: number, fallback?: number): string {
  if (tf != null && tr != null) return `\u00B1${tf.toFixed(1)}/\u00B1${tr.toFixed(1)}`;
  if (fallback != null) return `\u00B1${fallback.toFixed(1)}`;
  return "\u2014";
}

const GROUP_COLORS = [
  "#3b82f6", "#ef4444", "#f59e0b", "#10b981",
  "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
];

function buildGroupColorMap(results: SdmPrimerResult[]): Map<number, string> {
  const posCount = new Map<number, number>();
  for (const r of results) {
    const pos = r.aa_position;
    if (pos != null) {
      posCount.set(pos, (posCount.get(pos) ?? 0) + 1);
    }
  }
  const colorMap = new Map<number, string>();
  let idx = 0;
  for (const [pos, count] of posCount) {
    if (count >= 2) {
      colorMap.set(pos, GROUP_COLORS[idx % GROUP_COLORS.length]);
      idx++;
    }
  }
  return colorMap;
}

/** Forward primer with overlap(blue) + mutation(red) + downstream(black) coloring */
function ColoredFwdSeq({ seq, overlapLen }: {
  seq: string;
  overlapLen: number;
}) {
  const overlap = seq.slice(0, overlapLen);
  const codon = seq.slice(overlapLen, overlapLen + 3);
  const rest = seq.slice(overlapLen + 3);

  return (
    <span className="font-mono text-[10px] break-all">
      <span style={{ color: "#3b82f6" }}>{overlap}</span>
      <span style={{ color: "#ef4444", fontWeight: 600 }}>{codon}</span>
      <span>{rest}</span>
    </span>
  );
}

/** Shared row for candidate/custom primer in CandidatePopover */
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

/** Candidate comparison popover */
function CandidatePopover({
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
  const getAlternatives = useAppStore((s) => s.getAlternatives);
  const swapPrimer = useAppStore((s) => s.swapPrimer);
  const applyCustomPrimer = useAppStore((s) => s.applyCustomPrimer);
  const evaluateCustomPrimer = useAppStore((s) => s.evaluateCustomPrimer);
  const addCustomCandidate = useAppStore((s) => s.addCustomCandidate);
  const removeCustomCandidate = useAppStore((s) => s.removeCustomCandidate);
  const customCandidates = useAppStore((s) => s.customCandidates)[mutation] ?? [];

  // Load candidates on mount
  useEffect(() => {
    getAlternatives(mutation).then((c) => {
      setCandidates(c);
      setLoading(false);
    }).catch(() => {
      // Fallback: show current primer as sole candidate (e.g. MOCK_MODE)
      setCandidates([current]);
      setLoading(false);
    });
  }, [mutation, getAlternatives, current]);

  async function handleEvaluate() {
    const fwdInput = (customOverlap + customCodon + customDownstream).trim();
    const revInput = customRev.trim();
    if (!fwdInput && !revInput) return;
    // Fill missing side with current primer sequence
    const fwdSeq = fwdInput || current.forward_seq;
    const revSeq = revInput || current.reverse_seq;
    // Validate bases
    const fwdErr = validateSeq(fwdInput);
    const revErr = validateSeq(revInput);
    if (fwdErr || revErr) {
      setSeqError(`Invalid sequence: ${fwdErr || revErr}`);
      return;
    }
    setSeqError(null);
    // Duplicate check
    const isDup = customCandidates.some((c) => c.forward_seq === fwdSeq && c.reverse_seq === revSeq);
    if (isDup) {
      setSeqError("Duplicate custom primer — already added");
      return;
    }
    setEvaluating(true);
    const result = await evaluateCustomPrimer(mutation, fwdSeq, revSeq, fwdInput ? customOverlap.trim().length : (current.overlap_len ?? 20));
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
    >
      <div
        className="bg-white rounded-lg shadow-xl p-4 max-w-3xl max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">
            {mutation} — {candidates?.length ?? "..."} candidates
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
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

/** Hairpin / Homodimer detail popover */
function HairpinDetail({
  result,
  onClose,
}: {
  result: SdmPrimerResult;
  onClose: () => void;
}) {
  const rows = [
    { label: "Hairpin Fwd", tm: result.hairpin_tm_fwd ?? 0, dg: result.hairpin_dg_fwd ?? 0 },
    { label: "Hairpin Rev", tm: result.hairpin_tm_rev ?? 0, dg: result.hairpin_dg_rev ?? 0 },
    { label: "Homodimer Fwd", tm: result.homodimer_tm_fwd ?? 0, dg: result.homodimer_dg_fwd ?? 0 },
    { label: "Homodimer Rev", tm: result.homodimer_tm_rev ?? 0, dg: result.homodimer_dg_rev ?? 0 },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl p-4 min-w-[280px]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">
            {result.mutation} — Secondary Structure
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
          >
            ×
          </button>
        </div>

        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-gray-600 font-semibold">
              <th className="px-3 py-1.5 text-left">Type</th>
              <th className="px-3 py-1.5 text-right">Tm (°C)</th>
              <th className="px-3 py-1.5 text-right">dG (kcal/mol)</th>
              <th className="px-3 py-1.5 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-b border-gray-100">
                <td className="px-3 py-1.5">{r.label}</td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.tm > 0 ? r.tm.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.dg !== 0 ? r.dg.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-center">
                  {r.tm <= 0 ? (
                    <span className="text-gray-400">—</span>
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
          <div className="mt-3 text-[10px] text-gray-400 space-y-0.5">
            <div className="font-semibold text-gray-600">Warnings:</div>
            {result.warnings.map((w, i) => (
              <div key={i} className="text-yellow-700">{w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function OffTargetDetail({
  result,
  onClose,
}: {
  result: SdmPrimerResult;
  onClose: () => void;
}) {
  const fwdHits = result.offtarget_fwd ?? [];
  const revHits = result.offtarget_rev ?? [];
  const allHits = [
    ...fwdHits.map((h) => ({ ...h, primer: "Fwd" as const })),
    ...revHits.map((h) => ({ ...h, primer: "Rev" as const })),
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl p-4 min-w-[360px] max-w-lg max-h-[60vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">
            {result.mutation} — Off-Target Sites ({allHits.length})
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
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

/** Failed mutation popover — retry with adjusted parameters or manual primer input */
function FailedMutationPopover({
  failed,
  onClose,
}: {
  failed: FailedMutation;
  onClose: () => void;
}) {
  // Retry parameters — init from store
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

  // Manual input
  const [customOverlap, setCustomOverlap] = useState("");
  const [customCodon, setCustomCodon] = useState("");
  const [customDownstream, setCustomDownstream] = useState("");
  const [customRev, setCustomRev] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [seqError, setSeqError] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);

  const retryFailedMutation = useAppStore((s) => s.retryFailedMutation);
  const evaluateCustomPrimer = useAppStore((s) => s.evaluateCustomPrimer);
  const addDesignResult = useAppStore((s) => s.addDesignResult);

  async function handleRetry() {
    setRetrying(true);
    setRetryError(null);
    setCandidates([]);
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
      codon_strategy: storeCodon,
    });
    if (results.length === 0) {
      setRetryError("No candidates found with these parameters");
    } else {
      setCandidates(results);
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
    const result = await evaluateCustomPrimer(failed.mutation, fwdSeq, revSeq, customOverlap.trim().length);
    if (result) {
      addDesignResult(failed.mutation, result);
      onClose();
    }
    setEvaluating(false);
  }

  const inp = "w-14 h-5 text-[10px] border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl p-4 min-w-[440px] max-w-xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold text-red-700">{failed.mutation} — Design Failed</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg px-2">×</button>
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

const HEADER_TOOLTIPS: Record<string, string> = {
  rank: "Input order (EVOLVEpro: y_pred descending rank)",
  mutation: "Amino acid substitution. Click header to sort by aa position",
  forward_seq: "Full forward primer (overlap + mutation codon + downstream). Click to compare candidates",
  reverse_seq: "Full reverse primer. Click to compare candidates",
  fwd_len: "Forward primer length (bp)",
  rev_len: "Reverse primer length (bp)",
  tm_no_fwd: "Forward whole-primer Tm (SantaLucia 1998)",
  tm_no_rev: "Reverse whole-primer Tm (SantaLucia 1998)",
  tm_overlap: "Overlap region Tm - should be lower than Fwd/Rev Tm",
  tolerance_used: "Tm tolerance Fwd/Rev (each starts at +/-0.5, widens by 0.5 up to +/-3.0)",
  penalty: "Sum of Tm deviations + GC% penalty (lower is better)",
  candidate_count: "Unique forward / reverse candidates (click to compare if >1)",
  has_offtarget: "Off-target binding detected on template strand",
  hairpin: "Hairpin/Homodimer worst Tm (>40°C = warning)",
  gc_fwd: "Forward primer GC content (40-60% recommended)",
  gc_rev: "Reverse primer GC content (40-60% recommended)",
  wt_codon: "Wild-type codon at this position",
};

function makeColumns(groupColorMap: Map<number, string>, codonStrategy: "closest" | "optimal", swapped: Record<string, string>, customCandidates: Record<string, SdmPrimerResult[]>, rescuedMutations: Set<string>, removeDesignResult: (mutation: string, reason: string) => void) {
  return [
    col.accessor("rank", {
      header: "#",
      size: 35,
      enableSorting: false,
      cell: (info) => (
        <span className="text-gray-400">{info.getValue()}</span>
      ),
    }),
    col.accessor("mutation", {
      header: "Mutation",
      size: 90,
      sortingFn: (a, b) => {
        const posA = a.original.aa_position ?? 0;
        const posB = b.original.aa_position ?? 0;
        if (posA !== posB) return posA - posB;
        return a.original.rank - b.original.rank;
      },
      cell: (info) => {
        const row = info.row.original;
        const color = row.aa_position != null ? groupColorMap.get(row.aa_position) : undefined;
        const isRescued = rescuedMutations.has(row.mutation);
        return (
          <span className="font-mono font-medium flex items-center gap-1">
            <span>
              {info.getValue()}
              {color && (
                <span
                  className="inline-block ml-1 px-1 rounded text-[8px] font-semibold text-white align-middle"
                  style={{ backgroundColor: color }}
                >
                  Pos{row.aa_position}
                </span>
              )}
            </span>
            {isRescued && (
              <button
                className="ml-1 px-1 py-0.5 bg-red-100 text-red-600 rounded text-[8px] hover:bg-red-200 leading-none"
                title="Remove custom rescue — restore to Failed"
                onClick={(e) => {
                  e.stopPropagation();
                  removeDesignResult(row.mutation, "Manually removed custom rescue");
                }}
              >
                ✕
              </button>
            )}
          </span>
        );
      },
    }),
    col.accessor("forward_seq", {
      header: "Forward Primer",
      size: 220,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const row = info.row.original;
        const sw = swapped[row.mutation];
        const fwdEdited = sw === "fwd" || sw === "both";
        return (
          <span className={fwdEdited ? "bg-amber-100 rounded px-0.5" : ""}>
          <ColoredFwdSeq
            seq={info.getValue()}
            overlapLen={row.overlap_len ?? 0}
          />
          </span>
        );
      },
    }),
    col.accessor("reverse_seq", {
      header: "Reverse Primer",
      size: 200,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const sw = swapped[info.row.original.mutation];
        const revEdited = sw === "rev" || sw === "both";
        return (
        <span className={`font-mono text-[10px] break-all ${revEdited ? "bg-amber-100 rounded px-0.5" : ""}`}>
          {info.getValue()}
        </span>
        );
      },
    }),
    col.accessor("fwd_len", {
      header: "Fwd",
      size: 40,
    }),
    col.accessor("rev_len", {
      header: "Rev",
      size: 40,
    }),
    col.accessor("tm_no_fwd", {
      header: "Tm F",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_no_rev", {
      header: "Tm R",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_overlap", {
      header: "Tm Ov",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tolerance_used", {
      header: "Tol",
      size: 65,
      cell: (info) => {
        const row = info.row.original;
        return formatTolerance(row.tolerance_fwd, row.tolerance_rev, info.getValue());
      },
    }),
    col.accessor("penalty", {
      header: "Pen",
      size: 45,
      cell: (info) => {
        const val = info.getValue();
        return val != null ? val.toFixed(1) : "\u2014";
      },
    }),
    col.accessor("candidate_count", {
      header: "Cand",
      size: 50,
      sortingFn: (a, b) => {
        const customA = (customCandidates[a.original.mutation] ?? []).length;
        const customB = (customCandidates[b.original.mutation] ?? []).length;
        const aMax = Math.max((a.original.candidate_fwd_count ?? 0) + customA, (a.original.candidate_rev_count ?? 0) + customA);
        const bMax = Math.max((b.original.candidate_fwd_count ?? 0) + customB, (b.original.candidate_rev_count ?? 0) + customB);
        return aMax - bMax;
      },
      cell: (info) => {
        const row = info.row.original;
        const customLen = (customCandidates[row.mutation] ?? []).length;
        const fc = (row.candidate_fwd_count ?? 0) + customLen;
        const rc = (row.candidate_rev_count ?? 0) + customLen;
        if (fc <= 0 && rc <= 0) return "\u2014";
        return <span className="text-[10px]">{fc}/{rc}</span>;
      },
    }),
    col.accessor("has_offtarget", {
      header: "OT",
      size: 40,
      meta: { clickable: true, clickType: "offtarget" },
      cell: (info) => {
        const val = info.getValue();
        if (val == null) return "\u2014";
        return val ? (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700">!!</span>
        ) : (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">OK</span>
        );
      },
    }),
    col.display({
      id: "hairpin",
      header: "HP",
      size: 40,
      enableSorting: true,
      sortingFn: (a, b) => {
        const worstA = Math.max(a.original.hairpin_tm_fwd ?? 0, a.original.hairpin_tm_rev ?? 0, a.original.homodimer_tm_fwd ?? 0, a.original.homodimer_tm_rev ?? 0);
        const worstB = Math.max(b.original.hairpin_tm_fwd ?? 0, b.original.hairpin_tm_rev ?? 0, b.original.homodimer_tm_fwd ?? 0, b.original.homodimer_tm_rev ?? 0);
        return worstA - worstB;
      },
      meta: { clickable: true, clickType: "hairpin" },
      cell: (info) => {
        const row = info.row.original;
        const maxHp = Math.max(row.hairpin_tm_fwd ?? 0, row.hairpin_tm_rev ?? 0);
        const maxHd = Math.max(row.homodimer_tm_fwd ?? 0, row.homodimer_tm_rev ?? 0);
        const worst = Math.max(maxHp, maxHd);
        if (worst <= 0) return "\u2014";
        const warn = worst > 40;
        return (
          <span
            className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium cursor-pointer ${
              warn ? "bg-yellow-100 text-yellow-800" : "bg-gray-50 text-gray-400"
            }`}
          >
            {worst.toFixed(0)}
          </span>
        );
      },
    }),
    col.accessor("gc_fwd", {
      header: "GC% F",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("gc_rev", {
      header: "GC% R",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("wt_codon", {
      header: "WT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
    col.accessor("mt_codon", {
      header: "MT",
      size: 40,
      meta: {
        tooltip: codonStrategy === "closest"
          ? "Mutant codon (min. nucleotide changes from WT)"
          : "Mutant codon (E. coli optimal)",
      },
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
  ];
}

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const sorting = useAppStore((s) => s.tableSorting);
  const setSorting = useAppStore((s) => s.setTableSorting);
  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);
  const [hpDetail, setHpDetail] = useState<SdmPrimerResult | null>(null);
  const [otDetail, setOtDetail] = useState<SdmPrimerResult | null>(null);
  const [failedPopover, setFailedPopover] = useState<FailedMutation | null>(null);

  const rankedData = useMemo(
    () => designResults.map((r, i) => ({ ...r, rank: i + 1 })),
    [designResults],
  );

  const groupColorMap = useMemo(
    () => buildGroupColorMap(designResults),
    [designResults],
  );

  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const manuallySwapped = useAppStore((s) => s.manuallySwapped);
  const customCandidatesAll = useAppStore((s) => s.customCandidates);
  const rescuedMutations = useAppStore((s) => s.rescuedMutations);
  const removeDesignResult = useAppStore((s) => s.removeDesignResult);
  const columns = useMemo(
    () => makeColumns(groupColorMap, codonStrategy, manuallySwapped, customCandidatesAll, rescuedMutations, removeDesignResult),
    [groupColorMap, codonStrategy, manuallySwapped, customCandidatesAll, rescuedMutations, removeDesignResult],
  );

  const table = useReactTable({
    data: rankedData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const handleCellClick = useCallback((row: SdmPrimerResult & { rank: number }, columnId: string) => {
    if (columnId === "forward_seq" || columnId === "reverse_seq") {
      setPopover({ mutation: row.mutation, current: row });
    } else if (columnId === "hairpin") {
      const worst = Math.max(row.hairpin_tm_fwd ?? 0, row.hairpin_tm_rev ?? 0, row.homodimer_tm_fwd ?? 0, row.homodimer_tm_rev ?? 0);
      if (worst > 0) setHpDetail(row);
    } else if (columnId === "has_offtarget" && row.has_offtarget) {
      setOtDetail(row);
    }
  }, []);

  if (designResults.length === 0) {
    if (totalCount > 0 && failedMutations.length > 0) {
      return (
        <div className="h-full overflow-auto p-4">
          <div className="text-sm text-red-600 font-semibold mb-2">
            All {totalCount} mutations failed
          </div>
          <div className="text-[10px] text-red-600 font-mono flex flex-wrap gap-1">
            {failedMutations.map((f) => (
              <span
                key={f.mutation}
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-pointer hover:bg-red-200"
                title={`#${f.rank} | ${f.reason}`}
                onClick={() => setFailedPopover(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setFailedPopover(f)}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
          {failedPopover && (
            <FailedMutationPopover
              failed={failedPopover}
              onClose={() => setFailedPopover(null)}
            />
          )}
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Load a sequence file (FASTA / SnapGene) and enter mutations to design SDM primers
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`px-2 py-1.5 text-left font-semibold text-gray-600 border-b border-gray-300 ${
                    header.column.getCanSort() ? "cursor-pointer select-none hover:bg-gray-100" : ""
                  }`}
                  style={{ width: header.getSize() }}
                  title={(header.column.columnDef.meta as Record<string, string> | undefined)?.tooltip ?? HEADER_TOOLTIPS[header.column.id] ?? ""}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                  {header.column.getIsSorted() === "asc" ? " \u25B2" : ""}
                  {header.column.getIsSorted() === "desc" ? " \u25BC" : ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const isSwapped = !!manuallySwapped[row.original.mutation];
            return (
            <tr
              key={row.id}
              className={`hover:bg-gray-50 border-b border-gray-100 ${isSwapped ? "border-l-3 border-l-amber-400" : ""}`}
            >
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as Record<string, unknown> | undefined;
                const showClickable = !!meta?.clickable;
                return (
                  <td
                    key={cell.id}
                    className={`px-2 py-1 ${showClickable ? "cursor-pointer hover:bg-amber-50" : ""}`}
                    onClick={showClickable ? () => handleCellClick(row.original, cell.column.id) : undefined}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          );
          })}
        </tbody>
      </table>

      {failedMutations.length > 0 && (
        <div className="border-t border-gray-200 bg-red-50 px-3 py-2">
          <div className="text-xs font-semibold text-red-700 mb-1">
            Failed ({failedMutations.length}/{totalCount})
          </div>
          <div className="text-[10px] text-red-600 font-mono flex flex-wrap gap-1">
            {failedMutations.map((f) => (
              <span
                key={f.mutation}
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-pointer hover:bg-red-200"
                title={`#${f.rank} | ${f.reason}`}
                onClick={() => setFailedPopover(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setFailedPopover(f)}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
        </div>
      )}

      {designResults.length > 0 && (
        <div className="border-t border-gray-200 bg-gray-50 px-3 py-1.5 text-[10px] text-gray-400">
          {successCount}/{totalCount} designed
          {failedMutations.length > 0 && ` | ${failedMutations.length} failed`}
        </div>
      )}

      {popover && (
        <CandidatePopover
          mutation={popover.mutation}
          current={popover.current}
          onClose={() => setPopover(null)}
        />
      )}

      {hpDetail && (
        <HairpinDetail
          result={hpDetail}
          onClose={() => setHpDetail(null)}
        />
      )}

      {otDetail && (
        <OffTargetDetail
          result={otDetail}
          onClose={() => setOtDetail(null)}
        />
      )}

      {failedPopover && (
        <FailedMutationPopover
          failed={failedPopover}
          onClose={() => setFailedPopover(null)}
        />
      )}
    </div>
  );
}
