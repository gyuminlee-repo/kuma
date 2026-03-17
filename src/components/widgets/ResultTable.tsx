import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult } from "../../types/models";

const col = createColumnHelper<SdmPrimerResult & { rank: number }>();

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
    }).catch(() => setLoading(false));
  }, [mutation, getAlternatives]);

  async function handleEvaluate() {
    const fwdInput = (customOverlap + customCodon + customDownstream).trim();
    const revInput = customRev.trim();
    if (!fwdInput && !revInput) return;
    // Fill missing side with current primer sequence
    const fwdSeq = fwdInput || current.forward_seq;
    const revSeq = revInput || current.reverse_seq;
    // Duplicate check
    const isDup = customCandidates.some((c) => c.forward_seq === fwdSeq && c.reverse_seq === revSeq);
    if (isDup) {
      useAppStore.setState({ statusMessage: "Duplicate custom primer — already added" });
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
                  <tr
                    key={idx}
                    className={`border-b border-gray-100 ${rowClass}`}
                  >
                    <td className="px-2 py-1 text-center">
                      {idx + 1}
                      {isBest && <span className="ml-0.5 text-green-600 text-[8px]">best</span>}
                    </td>
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
                    <td className="px-2 py-1 text-center"
                      title={c.warnings?.length ? c.warnings.join("\n") : ""}
                    >
                      {c.penalty.toFixed(1)}
                    </td>
                    <td className={`px-2 py-1 text-center ${c.has_offtarget ? "cursor-pointer" : ""}`}
                      onClick={c.has_offtarget ? () => setOtDetailCand(c) : undefined}
                    >
                      {c.has_offtarget ? (
                        <span className="text-red-600 font-medium">!!</span>
                      ) : (
                        <span className="text-green-600">OK</span>
                      )}
                    </td>
                    <td className="px-2 py-1 text-center whitespace-nowrap">
                      <div className="flex gap-0.5 justify-center items-center">
                        {isCurrent && <span className="text-amber-600 text-[9px] mr-0.5">✓</span>}
                        <button className="px-1 py-0.5 bg-blue-500 text-white rounded text-[8px] hover:bg-blue-600" onClick={() => handleSwap(idx, "both")} title="Use both Fwd+Rev">Both</button>
                        <button className="px-1 py-0.5 bg-green-500 text-white rounded text-[8px] hover:bg-green-600" onClick={() => handleSwap(idx, "fwd")} title="Use Forward only">F</button>
                        <button className="px-1 py-0.5 bg-orange-500 text-white rounded text-[8px] hover:bg-orange-600" onClick={() => handleSwap(idx, "rev")} title="Use Reverse only">R</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {/* Custom evaluated primers */}
              {customCandidates.map((c, ci) => (
                <tr key={`custom-${ci}`} className="border-b border-gray-100 bg-purple-50">
                  <td className="px-2 py-1 text-center text-purple-600 text-[9px]">C{ci + 1}</td>
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
                  <td className="px-2 py-1 text-center"
                    title={c.warnings?.length ? c.warnings.join("\n") : ""}
                  >{c.penalty.toFixed(1)}</td>
                  <td className={`px-2 py-1 text-center ${c.has_offtarget ? "cursor-pointer" : ""}`}
                    onClick={c.has_offtarget ? () => setOtDetailCand(c) : undefined}
                  >
                    {c.has_offtarget ? <span className="text-red-600">!!</span> : <span className="text-green-600">OK</span>}
                  </td>
                  <td className="px-2 py-1 text-center whitespace-nowrap">
                    <div className="flex gap-0.5 justify-center">
                      <button className="px-1 py-0.5 bg-purple-500 text-white rounded text-[8px] hover:bg-purple-600" onClick={() => handleApplyCustom(c)} title="Apply this custom primer">Use</button>
                      <button className="px-1 py-0.5 bg-gray-400 text-white rounded text-[8px] hover:bg-gray-500" onClick={() => handleDeleteCustom(ci)} title="Remove">×</button>
                    </div>
                  </td>
                </tr>
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

function makeColumns(groupColorMap: Map<number, string>, codonStrategy: "closest" | "optimal", swapped: Record<string, string>) {
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
        return (
          <span className="font-mono font-medium">
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
        const aMax = Math.max(a.original.candidate_fwd_count ?? 0, a.original.candidate_rev_count ?? 0);
        const bMax = Math.max(b.original.candidate_fwd_count ?? 0, b.original.candidate_rev_count ?? 0);
        return aMax - bMax;
      },
      cell: (info) => {
        const row = info.row.original;
        const fc = row.candidate_fwd_count ?? 0;
        const rc = row.candidate_rev_count ?? 0;
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
  const columns = useMemo(
    () => makeColumns(groupColorMap, codonStrategy, manuallySwapped),
    [groupColorMap, codonStrategy, manuallySwapped],
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
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-help"
                title={`#${f.rank} | ${f.reason}`}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
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
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-help"
                title={`#${f.rank} | ${f.reason}`}
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
    </div>
  );
}
