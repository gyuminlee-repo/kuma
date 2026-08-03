"""8-class verdict classifier.

Priority (fail-first): LOWDEPTH -> FRAMESHIFT -> INDEL_EVENT (gate -> AMBIGUOUS) -> NO_CALL -> MANY -> MIXED -> WRONG_AA -> AMBIGUOUS -> PASS.

Invariant: no verdict counted as reproduced (PASS / AMBIGUOUS, see
``kuma_core.mame.detected``) is returned before the designed mutations have been
matched against the observed ones. The INDEL_EVENT gate therefore only awards
AMBIGUOUS to a well whose designed mutations are already confirmed.
"""

from __future__ import annotations

import re

from kuma_core.mame.ingest.codon_haplotype import codon_index_for_aa_position
from kuma_core.mame.models import (
    CompareParams,
    ExpectedCodonEvidence,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)

_AA_SUB_RE = re.compile(r"^([A-Z\*])(\d+)([A-Z\*])$")
_AA_DEL_RE = re.compile(r"^([A-Z\*])(\d+)(del|-)$")
_NT_INDEL_RE = re.compile(r"^(\d+)_INDEL$")

# A confident MIXED call needs the minor allele to be distinguishable from ONT
# error, which requires adequate depth. At or above ``min_read_count`` times this
# factor a mixed signal is reported MIXED; below it the well is reported LOWDEPTH
# (inconclusive) instead of a confident contamination call. Mirrors the LOWDEPTH
# read-count gate and applies only when both a read_count and min_read_count exist.
_MIXED_CONFIDENT_DEPTH_FACTOR = 3

# Codon depth below this fraction of the well read count is reported as a
# coverage shortfall rather than read as a measurement. A read that reaches the
# well has already passed the demux span and coverage gates, so it should supply
# every codon; when it does not, the alignment dropped the codon and "not seen"
# says nothing about the library. Half is a deliberately loose bound: the
# observed failure mode is an order of magnitude below the well depth, and ONT
# reads lose a few percent of codons to indel noise even when healthy.
_CODON_COVERAGE_SHORTFALL = 0.5


class ExpectedCoordinateMismatchError(ValueError):
    """Expected-mutation labels do not share a coordinate origin with the reference.

    Observed AA labels are emitted as ``{ref_aa}{pos}{query_aa}``, so the WT
    character of an observed label at a position IS the reference residue there.
    When an expected label claims a different WT residue at the same position,
    the KURO sheet numbering and the CDS numbering disagree (a tag, leader
    peptide, or plasmid offset). Every well on the plate would then be scored
    against the wrong residue while still producing clean PASS verdicts, so this
    is raised to abort the run rather than degraded per well.
    """


def parse_mutation_label(label: str) -> tuple[str, int, str] | None:
    """Parse a human-readable AA label into (wt, position, mt).

    Accepts `V5F` style substitutions and `K48del` / `K48-` style deletions.
    Returns None if the label cannot be parsed.
    """

    m = _AA_SUB_RE.match(label.strip())
    if m is not None:
        return m.group(1), int(m.group(2)), m.group(3)
    m = _AA_DEL_RE.match(label.strip())
    if m is not None:
        return m.group(1), int(m.group(2)), "-"
    return None


def _join(notes: list[str], note: str) -> str:
    """Join accumulated notes with a verdict-specific note, dropping blanks."""
    return "; ".join([n for n in (*notes, note) if n])


def _assert_expected_origin(
    expected_parsed: dict[int, tuple[str, str]],
    observed_parsed: dict[int, tuple[str, str]],
) -> None:
    """Raise when an expected label disagrees with the reference WT residue.

    Observed labels carry the reference residue as their WT character, so an
    observed position is direct evidence of ``ref_aa[pos - 1]``. Silence here was
    the failure mode: a KURO sheet numbered against a tagged or plasmid construct
    scored the whole plate one offset away from the CDS and still reported PASS.
    """
    for pos, (exp_wt, _exp_mt) in expected_parsed.items():
        if pos not in observed_parsed:
            continue
        ref_wt = observed_parsed[pos][0]
        if ref_wt == exp_wt:
            continue
        offsets = sorted(
            obs_pos - pos
            for obs_pos, (obs_wt, _mt) in observed_parsed.items()
            if obs_wt == exp_wt
        )
        hint = (
            f" A position carrying {exp_wt} sits at offset {offsets[0]:+d}"
            if len(offsets) == 1
            else (
                f" Candidate offsets carrying {exp_wt}: "
                f"{', '.join(f'{o:+d}' for o in offsets)}"
                if offsets
                else " No observed position carries the expected WT residue."
            )
        )
        raise ExpectedCoordinateMismatchError(
            f"expected mutation WT residue disagrees with the reference: "
            f"reference residue at position {pos} is {ref_wt}, expected label "
            f"claims {exp_wt}. Expected-mutation numbering and CDS numbering do "
            f"not share an origin (tag, leader peptide, or plasmid offset)."
            + hint
        )


def _positions(labels: list[str]) -> set[int]:
    out: set[int] = set()
    for label in labels:
        parsed = parse_mutation_label(label)
        if parsed is not None:
            out.add(parsed[1])
    return out


def _has_frameshift(translated: TranslatedRecord, window_bp: int) -> bool:
    indel_positions = [
        int(m.group(1))
        for nt in translated.observed_nt_changes
        if (m := _NT_INDEL_RE.match(nt)) is not None
    ]
    if len(indel_positions) < 2:
        return False
    indel_positions.sort()
    for i in range(len(indel_positions) - 1):
        if indel_positions[i + 1] - indel_positions[i] <= window_bp:
            return True
    return False




# ---------------------------------------------------------------------------
# Expected-codon read-level evidence
# ---------------------------------------------------------------------------
#
# A majority-vote consensus answers "what is the dominant molecule in this
# well". It cannot answer "was the designed variant introduced at all", and the
# two come apart whenever a designed clone is a minority. Measured on the IspS
# R560 plate: all nine designed variants are genuinely present in the reads at
# 0.16 to 1.56 percent while wild type holds 92.6 percent, so every one of them
# is reported WRONG_AA, which is indistinguishable from "the mutagenesis never
# worked". These helpers attach the read-level number so an operator can tell
# a failed reaction from a low frequency one.
#
# They never change the verdict. R560 IS a WRONG_AA well: the clone that grew is
# wild type. What changes is that the note now says so explicitly.


def _codon_coverage_warning(ev: ExpectedCodonEvidence) -> str:
    """Flag a codon the alignment barely covered, so 'not seen' is not misread."""
    if ev.well_read_count <= 0:
        return ""
    if ev.codon_depth >= ev.well_read_count * _CODON_COVERAGE_SHORTFALL:
        return ""
    return (
        f"codon coverage {ev.codon_depth}/{ev.well_read_count} of well reads, "
        "so absence here is inconclusive"
    )


def _describe_codon_evidence(ev: ExpectedCodonEvidence) -> str:
    """One human-readable clause for a single expected mutation."""
    if ev.unavailable_reason:
        return f"{ev.label} minor-allele evidence unavailable ({ev.unavailable_reason})"
    if ev.codon_depth == 0:
        return (
            f"expected {ev.label} (codon {ev.expected_codon}) has no read spanning "
            f"codon {ev.codon_index + 1} at full length"
            + (
                f" (well has {ev.well_read_count} reads)"
                if ev.well_read_count
                else ""
            )
        )
    if ev.count_is_upper_bound:
        return (
            f"expected {ev.label} (codon {ev.expected_codon}) below the retained "
            f"top-k: at most {ev.fraction * 100:.2f}% (<={ev.count}/{ev.codon_depth})"
        )
    if ev.count == 0:
        return (
            f"expected {ev.label} (codon {ev.expected_codon}) seen in no read "
            f"(0/{ev.codon_depth}); majority codon {ev.majority_codon} at "
            f"{ev.majority_fraction * 100:.1f}%"
        )
    return (
        f"expected {ev.label} (codon {ev.expected_codon}) seen at "
        f"{ev.fraction * 100:.2f}% ({ev.count}/{ev.codon_depth}); majority codon "
        f"{ev.majority_codon} at {ev.majority_fraction * 100:.1f}%"
    )


def _codon_evidence_note(evidence: list[ExpectedCodonEvidence]) -> str:
    parts: list[str] = []
    for ev in evidence:
        clause = _describe_codon_evidence(ev)
        warn = "" if ev.unavailable_reason else _codon_coverage_warning(ev)
        parts.append(f"{clause} [{warn}]" if warn else clause)
    return "; ".join(parts)


def _collect_codon_evidence(
    translated: TranslatedRecord,
    expected_mutations: list[str],
    expected_codons: dict[str, str] | None,
    cds_start: int,
) -> list[ExpectedCodonEvidence]:
    """Look up each expected mutation in this well's codon-haplotype sidecar.

    Returns an empty list when the caller supplied no design codons at all,
    which keeps every existing caller byte-identical. Once codons ARE supplied,
    every expected label yields an entry, including the ones that could not be
    answered: a missing sidecar has to be visible, not absent.
    """
    if not expected_codons:
        return []

    haplotypes = translated.barcode.codon_haplotypes
    out: list[ExpectedCodonEvidence] = []
    for label in expected_mutations:
        parsed = parse_mutation_label(label)
        if parsed is None:
            continue
        _wt, pos, _mt = parsed
        codon_seq = (expected_codons.get(label) or "").upper()

        def _blank(reason: str, index: int = -1) -> ExpectedCodonEvidence:
            return ExpectedCodonEvidence(
                label=label,
                expected_codon=codon_seq,
                codon_index=index,
                codon_depth=0,
                count=0,
                count_is_upper_bound=False,
                majority_codon="",
                majority_count=0,
                well_read_count=int(translated.barcode.read_count or 0),
                unavailable_reason=reason,
            )

        if len(codon_seq) != 3 or any(c not in "ACGT" for c in codon_seq):
            out.append(_blank("design carries no unambiguous mutant codon"))
            continue
        if haplotypes is None:
            out.append(
                _blank(
                    "no codon-haplotype sidecar for this well; re-run "
                    "demux/consensus to produce one"
                )
            )
            continue
        index = codon_index_for_aa_position(
            pos, cds_start, haplotypes.frame_offset
        )
        if index is None:
            out.append(
                _blank(
                    f"CDS start {cds_start} does not sit on the recorded codon "
                    f"grid (offset {haplotypes.frame_offset})"
                )
            )
            continue
        obs = haplotypes.lookup(index, codon_seq)
        if obs is None:
            out.append(
                _blank("codon lies outside the recorded reference grid", index)
            )
            continue
        out.append(
            ExpectedCodonEvidence(
                label=label,
                expected_codon=codon_seq,
                codon_index=index,
                codon_depth=obs.depth,
                count=obs.count,
                count_is_upper_bound=not obs.exact,
                majority_codon=obs.majority_seq,
                majority_count=obs.majority_count,
                well_read_count=int(translated.barcode.read_count or 0),
            )
        )
    return out


def classify_verdict(
    translated: TranslatedRecord,
    expected_mutations: list[str],
    params: CompareParams,
    expected_codons: dict[str, str] | None = None,
    cds_start: int = 0,
) -> VerdictRecord:
    """Return a VerdictRecord for the given translated record and expected list.

    ``expected_codons`` maps an AA label (``R560L``) to the mutant codon the
    design calls for. The key is the label and not the position because a
    saturation library puts many mutant codons on one position. Supplying it turns on read-level minor-allele reporting: every
    returned record carries ``expected_codon_evidence``, and the two WRONG_AA
    branches that say "missing" or "mismatched" qualify that with the measured
    frequency. Omitting it (the default) leaves behaviour exactly as before.

    The evidence is advisory. It is attached to whatever verdict the classifier
    reached and never redirects it.
    """
    evidence = _collect_codon_evidence(
        translated, list(expected_mutations), expected_codons, cds_start
    )
    record = _classify_verdict(translated, expected_mutations, params, evidence)
    record.expected_codon_evidence = evidence
    return record


def _classify_verdict(
    translated: TranslatedRecord,
    expected_mutations: list[str],
    params: CompareParams,
    evidence: list[ExpectedCodonEvidence],
) -> VerdictRecord:
    """Verdict decision proper. ``evidence`` only ever reaches verdict_notes."""

    notes: list[str] = []

    observed = list(translated.observed_aa_changes)

    expected_parsed: dict[int, tuple[str, str]] = {}
    for label in expected_mutations:
        parsed = parse_mutation_label(label)
        if parsed is not None:
            wt, pos, mt = parsed
            expected_parsed[pos] = (wt, mt)

    observed_parsed: dict[int, tuple[str, str]] = {}
    for label in observed:
        parsed = parse_mutation_label(label)
        if parsed is not None:
            wt, pos, mt = parsed
            observed_parsed[pos] = (wt, mt)

    # Coordinate-origin guard. Runs before every verdict gate so a numbering
    # mismatch aborts the run on the first well that carries evidence, instead of
    # scoring the whole plate against the wrong residue and reporting clean PASS.
    _assert_expected_origin(expected_parsed, observed_parsed)

    # 1) LOWDEPTH — use real read depth when callers opt into a read-count
    # threshold and the consensus header carries depth=N metadata; otherwise
    # preserve the legacy file-size proxy behavior.
    if (
        params.min_read_count is not None
        and translated.barcode.read_count is not None
        and translated.barcode.read_count < params.min_read_count
    ):
        notes.append(
            f"read_count={translated.barcode.read_count} < "
            f"min_read_count={params.min_read_count}"
        )
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.LOWDEPTH,
            verdict_notes="; ".join(notes),
        )

    # Frame is a property of the called molecule, so the gate reads the net indel
    # of the CONSENSUS, never the median over raw reads. ONT reads carry a high
    # per-read indel error rate in homopolymers; on a real plate the per-read
    # median sat at -1 bp for 253 of 288 wells whose consensus aligned to the
    # reference gap-free (CIGAR 1683M at depth 4,982-6,560), and every one of
    # them was failed as a frameshift. Averaging that per-read error away is
    # precisely what building a consensus is for.
    net_indel = translated.barcode.consensus_net_indel_bp
    if net_indel is not None and net_indel % 3 != 0:
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.FRAMESHIFT,
            verdict_notes=(
                f"consensus net indel {net_indel} bp not divisible by 3 (frameshift)"
            ),
        )

    # INDEL EVENT gate — surface indel-bearing wells that evade the existing
    # FRAMESHIFT check.  The existing _has_frameshift uses {pos}_INDEL markers
    # in observed_nt_changes, but those markers are produced only when
    # consensus_seq is longer than the reference (which never happens with the
    # reference-length consensus caller). This gate uses raw pileup evidence
    # (max_indel_event_fraction) instead.  Priority is between LOWDEPTH and
    # NO_CALL so that a deletion-dominant well (consensus N fraction elevated)
    # is flagged AMBIGUOUS+indel note rather than NO_CALL — giving the user
    # a more actionable signal.
    #
    # The gate only awards AMBIGUOUS when this well has already reproduced every
    # designed mutation with the correct MT. AMBIGUOUS counts as `detected` in
    # detected.py and ranks first in select/best_pick.py, both of which rest on
    # the contract "every expected mutation was matched". A gate that returned
    # AMBIGUOUS before looking at the designed mutations broke that contract and
    # inflated recovery_rate with wells whose designed variant was absent. When
    # the designed mutations are NOT confirmed the gate no longer returns; the
    # indel signal is carried forward as a note and the remaining checks
    # (NO_CALL / FRAMESHIFT / MANY / MIXED / WRONG_AA) decide the verdict.
    # An empty expected list is vacuously confirmed, preserving the gate for
    # wells analyzed without a design (e.g. WT controls).
    if (
        params.max_indel_event_fraction is not None
        and translated.barcode.max_indel_event_fraction
        > params.max_indel_event_fraction
    ):
        unconfirmed = [
            f"{wt}{pos}{mt}"
            for pos, (wt, mt) in expected_parsed.items()
            if pos not in observed_parsed or observed_parsed[pos][1] != mt
        ]
        # Informational run-length annotation. The deletion-majority run length
        # distinguishes an isolated single-position alignment artifact (run=1)
        # from a multi-position true deletion (run>=2), and flags an
        # insertion-driven gate (run=0). Does not change the gate decision.
        del_run = translated.barcode.max_del_run_length
        if del_run == 0:
            run_note = " (insertion-driven)"
        elif del_run == 1:
            run_note = (
                " (deletion at single isolated position, run=1, "
                "review for alignment artifact)"
            )
        else:
            run_note = f" (deletion {del_run}-bp contiguous run)"
        indel_note = (
            "indel event signal: "
            f"max_indel_event_fraction="
            f"{translated.barcode.max_indel_event_fraction:.3f} > "
            f"threshold={params.max_indel_event_fraction:.3f}; "
            f"n_indel_event_positions="
            f"{translated.barcode.n_indel_event_positions}"
            + run_note
        )
        if not unconfirmed:
            return VerdictRecord(
                translated=translated,
                expected_mutations=list(expected_mutations),
                verdict=VerdictClass.AMBIGUOUS,
                verdict_notes=indel_note,
            )
        notes.append(indel_note)

    # NO_CALL — consensus carries too many N (ambiguous) positions to trust the
    # AA calls. Distinct from LOWDEPTH (a genuine read-count shortage, above):
    # here depth can be ample but the consensus is dominated by no-call bases.
    #
    # A well whose consensus_n_fraction is not evaluable skips this gate in both
    # directions: it is neither failed on a number that means something else nor
    # quietly passed as if it were clean. The reason travels with the well in
    # verdict_notes so the operator can act on it.
    if (
        params.max_consensus_n_fraction is not None
        and not translated.barcode.consensus_n_fraction_evaluable
    ):
        notes.append(
            "consensus_n_fraction not evaluable (legacy consensus file without "
            "a covered-scoped N fraction); N-fraction gate skipped, re-run "
            "consensus to restore it"
        )
    elif (
        params.max_consensus_n_fraction is not None
        and translated.barcode.consensus_n_fraction
        > params.max_consensus_n_fraction
    ):
        notes.append(
            "consensus_n_fraction="
            f"{translated.barcode.consensus_n_fraction:.3f} > "
            f"max_consensus_n_fraction={params.max_consensus_n_fraction:.3f}"
        )
        if translated.n_no_call_aa > 0:
            notes.append(f"no_call_aa={translated.n_no_call_aa}")
        if translated.barcode.n_low_depth_positions > 0:
            notes.append(
                f"low_depth_positions={translated.barcode.n_low_depth_positions}"
            )
        if translated.barcode.n_low_quality_bases > 0:
            notes.append(
                f"low_quality_bases={translated.barcode.n_low_quality_bases}"
            )
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.NO_CALL,
            verdict_notes="; ".join(notes),
        )

    # Fallback-only file-size gate. Real depth lives in the consensus
    # `depth=N` header (read_count). A per-well consensus FASTA is gene-length
    # bound (~1.8 KB for the same amplicon across every well), so comparing it
    # against a multi-KB volume threshold falsely flagged depth-sufficient wells
    # as LOWDEPTH. Wells that carry a real read_count are judged by the
    # read_count gate above; this proxy fires only when depth=N is genuinely
    # absent (read_count is None), e.g. directly-constructed records or legacy
    # consensus files lacking the depth header.
    if (
        translated.barcode.read_count is None
        and translated.barcode.file_size_kb < params.min_file_size_kb
    ):
        notes.append(
            f"file_size_kb={translated.barcode.file_size_kb:.2f} < "
            f"min_file_size_kb={params.min_file_size_kb}"
        )
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.LOWDEPTH,
            verdict_notes="; ".join(notes),
        )

    if _has_frameshift(translated, params.frameshift_window_bp):
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.FRAMESHIFT,
            verdict_notes=_join(
                notes, "consecutive NT indels within frameshift window"
            ),
        )

    # 3) MANY — too many AA changes to be a clean call. The cutoff is an
    # *excess* gate, not an absolute one: a well can never be MANY when it
    # carries no more changes than its own design calls for. Comparing the raw
    # observed count against the cutoff misclassified legitimate multi-site
    # (e.g. combinatorial) designs as MANY even when observed == expected
    # exactly. Guarding on len(observed) > len(expected_mutations) keeps the
    # single-site behaviour (expected 1, observed 6 with cutoff 5 -> MANY)
    # while letting a perfect N-site well proceed to the expected/observed
    # comparison.
    if (
        len(observed) > params.many_mutation_cutoff
        and len(observed) > len(expected_mutations)
    ):
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.MANY,
            verdict_notes=_join(
                notes,
                f"observed {len(observed)} AA changes > cutoff "
                f"{params.many_mutation_cutoff}",
            ),
        )

    # MIXED — within-well contamination. A substantial second allele (for
    # example 51/49) means majority consensus can look exact while the well is
    # actually mixed. Detected before WRONG_AA so contamination is reported as
    # its own class rather than being masked by an AA-mismatch verdict.
    if translated.barcode.n_mixed_positions > 0:
        # MIXED confidence floor: below min_read_count x factor the minor allele
        # cannot be distinguished from ONT error, so report LOWDEPTH
        # (inconclusive) rather than a confident contamination call. Recovery is
        # unaffected (both verdicts are non-PASS); only the failure reason changes.
        rc = translated.barcode.read_count
        mixed_floor = (
            params.min_read_count * _MIXED_CONFIDENT_DEPTH_FACTOR
            if params.min_read_count is not None
            else None
        )
        if mixed_floor is not None and rc is not None and rc < mixed_floor:
            return VerdictRecord(
                translated=translated,
                expected_mutations=list(expected_mutations),
                verdict=VerdictClass.LOWDEPTH,
                verdict_notes=(
                    "mixed signal at insufficient depth: "
                    f"read_count={rc} < {mixed_floor} "
                    f"(min_read_count={params.min_read_count} x "
                    f"{_MIXED_CONFIDENT_DEPTH_FACTOR}); n_mixed_positions="
                    f"{translated.barcode.n_mixed_positions}, "
                    "max_minor_allele_fraction="
                    f"{translated.barcode.max_minor_allele_fraction:.3f}"
                ),
            )
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.MIXED,
            verdict_notes=_join(
                notes,
                "mixed consensus signal: "
                f"{translated.barcode.n_mixed_positions} positions, "
                "max_minor_allele_fraction="
                f"{translated.barcode.max_minor_allele_fraction:.3f}",
            ),
        )

    # 4) WRONG_AA — expected position hit but MT mismatches.
    for pos, (exp_wt, exp_mt) in expected_parsed.items():
        if pos in observed_parsed:
            obs_wt, obs_mt = observed_parsed[pos]
            if obs_mt != exp_mt:
                hit = [
                    ev for ev in evidence if ev.label == f"{exp_wt}{pos}{exp_mt}"
                ]
                return VerdictRecord(
                    translated=translated,
                    expected_mutations=list(expected_mutations),
                    verdict=VerdictClass.WRONG_AA,
                    verdict_notes=_join(
                        notes,
                        _join(
                            [
                                f"expected {exp_wt}{pos}{exp_mt}, "
                                f"observed {obs_wt}{pos}{obs_mt}"
                            ],
                            _codon_evidence_note(hit),
                        ),
                    ),
                )

    expected_positions = set(expected_parsed.keys())
    observed_positions = set(observed_parsed.keys())

    # All expected mutations must be present with matching MT to proceed.
    missing_expected = [
        f"{wt}{pos}{mt}" for pos, (wt, mt) in expected_parsed.items() if pos not in observed_parsed
    ]
    if missing_expected:
        # Missing an expected position = not a PASS; treat as WRONG_AA-style failure.
        #
        # "missing" here is a statement about the CONSENSUS, and on its own it
        # conflates two different laboratory outcomes: the mutagenesis produced
        # nothing, or it produced a clone that lost the population. The codon
        # evidence separates them, so it is appended whenever it exists.
        missing_set = set(missing_expected)
        hits = [ev for ev in evidence if ev.label in missing_set]
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.WRONG_AA,
            verdict_notes=_join(
                notes,
                _join(
                    [f"missing expected: {', '.join(missing_expected)}"],
                    _codon_evidence_note(hits),
                ),
            ),
        )

    # 5) AMBIGUOUS — expected positions are all matched, but extra AA changes
    #    (including deletions) fall within the ±indel_window_codon window.
    extra_positions = observed_positions - expected_positions
    window_hits: list[str] = []
    for pos in sorted(extra_positions):
        for exp_pos in expected_positions:
            if abs(pos - exp_pos) <= params.indel_window_codon:
                obs_wt, obs_mt = observed_parsed[pos]
                tag = f"{obs_wt}{pos}{obs_mt}"
                window_hits.append(
                    f"{tag} within window(\u00b1{params.indel_window_codon} codon "
                    f"of {list(expected_parsed.keys())[0]})"
                    if len(expected_parsed) == 1
                    else f"{tag} within \u00b1{params.indel_window_codon} codon of {exp_pos}"
                )
                break
    if window_hits:
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.AMBIGUOUS,
            verdict_notes=_join(notes, "; ".join(window_hits)),
        )

    # Any remaining extras outside the window disqualify a clean PASS.
    if extra_positions:
        tags = [
            f"{observed_parsed[p][0]}{p}{observed_parsed[p][1]}" for p in sorted(extra_positions)
        ]
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.WRONG_AA,
            verdict_notes=_join(
                notes, f"unexpected extra mutations: {', '.join(tags)}"
            ),
        )

    # 6) PASS — observed exactly matches expected.
    return VerdictRecord(
        translated=translated,
        expected_mutations=list(expected_mutations),
        verdict=VerdictClass.PASS,
        # Accumulated notes must survive a PASS: a skipped-gate advisory is only
        # actionable if it reaches the well it applies to.
        verdict_notes="; ".join(notes),
    )
