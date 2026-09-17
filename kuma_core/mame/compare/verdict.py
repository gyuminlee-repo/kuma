"""8-class verdict classifier.

Priority (fail-first): LOWDEPTH -> FRAMESHIFT -> INDEL_EVENT (gate -> AMBIGUOUS) -> NO_CALL -> MANY -> MIXED -> WRONG_AA -> AMBIGUOUS -> PASS.

Invariant: no verdict counted as reproduced (PASS / AMBIGUOUS, see
``kuma_core.mame.detected``) is returned before the designed mutations have been
matched against the observed ones. The INDEL_EVENT gate therefore only awards
AMBIGUOUS to a well whose designed mutations are already confirmed.
"""

from __future__ import annotations

import re

from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
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
#
# THIS VALUE IS OURS. Oxford Nanopore publishes no minor-allele threshold and no
# depth for calling a well mixed, so there is no vendor figure to follow here the
# way ``min_read_count`` follows ``minimum_mean_depth`` (see ``models.py``).
#
# What the floor has to defend is the 0.20 minor-allele gate in
# ``ingest/consensus.py`` (``mix_minor_fraction_threshold``), not an arbitrary
# notion of confidence. A position is called mixed only when the second base
# reaches 20% of ACGT depth, so the question is at what depth run noise can fake
# 20%. Taking the noisiest position measured on the 260729 ispS run (0.054, with
# a per-position median of 0.003) as the per-read error rate and 1500 positions
# per amplicon, the binomial tail gives the expected number of falsely mixed
# positions per well:
#
#     depth  30 -> 6 reads clear 20% -> 7.2 per well
#     depth  45 -> 9 reads          -> 0.88
#     depth  60 -> 12 reads         -> 0.11
#     depth  90 -> 18 reads         -> 0.002
#
# 90 sits where that curve has already flattened, so it is adequate for a 20%
# gate rather than thin. An earlier version of this comment called it thin by
# comparing against Moller et al. 2023 (doi:10.1128/spectrum.02728-22), which
# sequenced each amplicon to >1000x. That comparison does not transfer: the
# >1000x there buys a 6.5% detection limit, and resolving 6.5% needs far more
# depth than resolving 20%.
#
# Two caveats keep this an estimate rather than a calibration. The binomial
# assumes independent per-read error, while ONT error is context-systematic
# (homopolymers, strand bias), and a position with systematic 15% error is never
# fixed by depth. And the noise figures come from one amplicon on one run. Both
# push the open question onto the 0.20 gate, not onto this factor: a true
# mixture between the noise floor and 20% is invisible whatever the depth. Moving
# the gate is the change that would need subsampled real runs (the way the indel
# gate was calibrated from bench_v2) plus Moller-scale depth, and it would
# reclassify wells in every existing project and move the result contract.
#
# A third caveat, and the one this module cannot see for itself: THE DERIVATION
# ABOVE IS TIED TO AN AMPLICON LENGTH. The "per well" column is the per-position
# binomial tail multiplied by 1500 positions, so at the same depth a 500 bp
# amplicon runs a third of the trials and lands a third of the falsely mixed
# positions, while a 4500 bp one lands three times as many. Nothing here reads a
# reference length or a position count, so the factor is applied to every run as
# if it were the one the table was computed for. That premise is measured and
# reported where the run-level numbers live (``run_quality.py``, finding
# ``mixed_depth_factor_amplicon_scale``). Reported and never enforced: the thing
# that would have to move is the factor, and moving it reclassifies wells.
_MIXED_CONFIDENT_DEPTH_FACTOR = 3

#: Positions per amplicon the table above was computed over. Exported so the
#: run-level check compares against the number the derivation actually used,
#: rather than a second copy of it that can drift away from this comment.
MIXED_FACTOR_ASSUMED_POSITIONS = 1500


def gate_consensus_n_fraction(barcode: BarcodeRecord) -> tuple[float, int]:
    """Return the N fraction the NO_CALL gate judges, and the positions excluded.

    ``consensus_n_fraction`` answers "how much of the covered amplicon came back
    as 'N'". Every reader of that number keeps it: it is written to the consensus
    FASTA header, restored by ``ingest/fasta_parser.py``, exported to the
    workbook, and the threshold calibration on record was measured against it.
    Redefining it would silently change what past records mean, so it is left
    alone and only the gate's INPUT is narrowed here.

    Only ``n_no_call_deletion_majority`` is a decided deletion: it counts the
    covered no-call positions with strictly more than half of reads voting DEL.
    The broader deletion bucket also contains plurality and exact ties, which
    remain unresolved. The total deletion-majority count cannot substitute for
    this subset because it includes positions below the coverage threshold.

    The exclusion is computed as a ratio of the counts rather than by rebuilding
    ``n_covered_positions``. The denominator is not carried on ``BarcodeRecord``
    and recovering it would mean assuming the stored sequence length equals the
    reference length. Scaling by ``(n_nc - deletion) / n_nc`` needs no
    denominator, and the distinction that matters at the shipped threshold of
    0.0 (zero versus nonzero) stays exact even though a header round-trip keeps
    only three decimals of the fraction itself.

    Missing strict-subset metadata (legacy files) or an inconsistent subset
    leaves the reported fraction unchanged; neither proves a safe exclusion.

    Returns ``(fraction, n_excluded_positions)``.
    """
    n_nc = (
        barcode.n_no_call_zero_depth
        + barcode.n_no_call_deletion
        + barcode.n_no_call_ambiguous
        + barcode.n_no_call_no_majority
    )
    n_excluded = barcode.n_no_call_deletion_majority
    if (
        n_nc <= 0
        or n_excluded is None
        or not 0 < n_excluded <= barcode.n_no_call_deletion <= n_nc
    ):
        return barcode.consensus_n_fraction, 0
    kept = n_nc - n_excluded
    return (
        barcode.consensus_n_fraction * kept / n_nc,
        n_excluded,
    )


def gate_mixed_positions(barcode: BarcodeRecord) -> tuple[int, int, str]:
    """Return the mixed-position count the MIXED gate judges, and what it dropped.

    The twin of ``gate_consensus_n_fraction`` above, for the same reason and with
    the same rule: the REPORTED field is left alone and only the gate's INPUT is
    narrowed. ``n_mixed_positions`` stays what it has always been, is written to
    the consensus FASTA header, restored by ``ingest/fasta_parser.py``, and
    exported; redefining it would change what past records mean.

    What has to be narrowed is this. ``ingest/consensus.py`` measures the minor
    allele over A/C/G/T depth alone (``acgt = counts[:, :4]``), so reads voting
    for a DELETION are not in the denominator, while mix-eligibility is decided
    on the full depth. At a position whose reads mostly voted "this base is
    absent" the fraction is therefore computed over the thin remainder and clears
    0.20 on a handful of reads. Measured on well ``1_5`` of the 260729 ispS run:
    reference position 669 reports ``minor_fraction=0.368`` at an ACGT depth of
    87 while the well carries 3908 reads, i.e. about 32 reads over a spanning
    depth near 174, which is 0.18 and under the gate. The well is not mixed; its
    designed substitution simply did not go in. Because MIXED sits above
    WRONG_AA, the miscount hid that.

    A deletion-majority position is a decided call, exactly as in the N-fraction
    twin, and ``del_majority_positions`` already names those coordinates. Both
    lists are 1-based (``models.py`` ``NoisyPosition``,
    ``ingest/consensus.py`` converts once at the reporting boundary), so they
    intersect without conversion.

    WHICH positions are the mixed ones is recoverable without this layer knowing
    ``mix_minor_fraction_threshold``. ``noisy_positions`` is the top-K prefix of
    the eligible positions ranked by minor fraction DESCENDING, and the mixed
    ones are by definition those at or above a threshold, so the first
    ``n_mixed_positions`` entries are exactly the mixed set whenever the list is
    long enough to hold them. ``parse_noisy_positions`` keeps the written order
    and re-sorts nothing, so this survives a header round-trip.

    Two cases give up and return the shipped count with a reason:

    * the list is shorter than ``n_mixed_positions`` (report budget), so the
      mixed set cannot be named. The exception is ``n_mixed_positions >
      n_del_majority_positions``: there are then more mixed positions than there
      are deletion-majority positions in the whole well, so the gate stays open
      whatever the intersection is, and the shipped count is already the answer.
    * ``n_del_majority_positions`` is nonzero while ``del_majority_positions`` is
      empty, which means the deletion runs exceeded ``DEL_RUN_REPORT_BUDGET`` and
      the coordinates were not written. Empty there means "not reported", never
      "none".

    A record with no deletion majority, including every consensus file written
    before these keys existed, gets its count back untouched.

    Returns ``(gated_count, n_excluded_positions, reason)``; *reason* is ``""``
    when nothing was given up.
    """
    n_mixed = barcode.n_mixed_positions
    n_del = barcode.n_del_majority_positions
    if n_mixed <= 0 or n_del <= 0:
        return n_mixed, 0, ""
    if not barcode.del_majority_positions:
        return (
            n_mixed,
            0,
            f"mixed gate not narrowed: {n_del} deletion-majority position"
            f"{'s' if n_del != 1 else ''} counted but their coordinates were "
            "not reported (over the consensus deletion-run budget)",
        )
    if n_mixed > len(barcode.noisy_positions):
        if n_mixed > n_del:
            return n_mixed, 0, ""
        return (
            n_mixed,
            0,
            f"mixed gate not narrowed: {n_mixed} mixed positions cannot be "
            f"named from a {len(barcode.noisy_positions)}-entry noisy-position "
            "sample",
        )
    mixed_positions = {p.position for p in barcode.noisy_positions[:n_mixed]}
    n_excluded = len(mixed_positions & set(barcode.del_majority_positions))
    return n_mixed - n_excluded, n_excluded, ""


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


def read_at_position(translated: TranslatedRecord, pos: int) -> str:
    """Return what the well read at 1-based AA position *pos*.

    One of: the observed label sitting at *pos*, ``"WT"``, ``"no call"`` or
    ``"not covered"``.

    Why this cannot be inferred from an empty ``observed_aa_changes``: the
    translator keeps an N-bearing codon out of that list (it becomes 'X' in
    ``aa_sequence`` and is counted in ``n_no_call_aa``), so "no label here" means
    either the reference residue or no call at all. Only ``aa_sequence`` tells
    them apart. It carries one character per reference codon, so index
    ``pos - 1`` is the same coordinate the labels use. A gapped codon ('-') always
    has a ``del`` label and is caught by the first branch; a query that ended
    early leaves ``aa_sequence`` short, which reads as not covered.
    """

    for label in translated.observed_aa_changes:
        parsed = parse_mutation_label(label)
        if parsed is not None and parsed[1] == pos:
            return label
    seq = translated.aa_sequence
    if not 0 < pos <= len(seq):
        return "not covered"
    residue = seq[pos - 1]
    if residue == "X":
        return "no call"
    if residue == "-":
        # Unreachable through the translator (a gap always carries a del label),
        # kept so a hand-built record can never report a gap as WT.
        return "not covered"
    return "WT"


def expected_site_reads(
    translated: TranslatedRecord, expected_mutations: list[str]
) -> list[tuple[str, int, str]]:
    """Return ``(label, position, read)`` for every designed site of a well.

    *read* is :func:`read_at_position` at that site. Sites are keyed by position
    exactly as :func:`classify_verdict` builds ``expected_parsed``: a label that
    does not parse is skipped, and when two labels share a position the later
    label wins while the site keeps the place of its first appearance. The
    missing-expected WRONG_AA note, the Excel detected cell and the serialized
    ``expected_site_reads`` payload all read this, so the three cannot disagree
    about which sites a well was designed at.
    """

    sites: dict[int, str] = {}
    for label in expected_mutations:
        parsed = parse_mutation_label(label)
        if parsed is not None:
            sites[parsed[1]] = label
    return [
        (label, pos, read_at_position(translated, pos)) for pos, label in sites.items()
    ]


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


def classify_verdict(
    translated: TranslatedRecord,
    expected_mutations: list[str],
    params: CompareParams,
) -> VerdictRecord:
    """Return a VerdictRecord for the given translated record and expected list."""

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
    #
    # The number compared here is narrowed by gate_consensus_n_fraction: a
    # position the reads agreed is DELETED is a decided call and does not count
    # toward "too ambiguous to score". The reported consensus_n_fraction is
    # unchanged and still appears in the note.
    if (
        params.max_consensus_n_fraction is not None
        and not translated.barcode.consensus_n_fraction_evaluable
    ):
        notes.append(
            "consensus_n_fraction not evaluable (legacy consensus file without "
            "a covered-scoped N fraction); N-fraction gate skipped, re-run "
            "consensus to restore it"
        )
    elif params.max_consensus_n_fraction is not None and (
        gate_n_fraction := gate_consensus_n_fraction(translated.barcode)
    )[0] > params.max_consensus_n_fraction:
        gate_fraction, n_excluded = gate_n_fraction
        notes.append(
            "consensus_n_fraction="
            f"{translated.barcode.consensus_n_fraction:.3f} > "
            f"max_consensus_n_fraction={params.max_consensus_n_fraction:.3f}"
        )
        if n_excluded > 0:
            notes.append(
                f"gate fraction={gate_fraction:.3f} after excluding "
                f"{n_excluded} deletion-majority no-call position"
                f"{'s' if n_excluded != 1 else ''}"
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
    #
    # The count compared here is narrowed by gate_mixed_positions: a position the
    # reads agreed is DELETED has its minor fraction measured over the thin
    # remaining A/C/G/T pool, so it clears the 0.20 gate on a handful of reads
    # without the well being mixed. The reported n_mixed_positions is unchanged
    # and still appears in the note.
    gate_n_mixed, n_mixed_excluded, mixed_gate_reason = gate_mixed_positions(
        translated.barcode
    )
    if mixed_gate_reason:
        notes.append(mixed_gate_reason)
    if n_mixed_excluded > 0:
        notes.append(
            f"mixed gate count={gate_n_mixed} after excluding "
            f"{n_mixed_excluded} mixed position"
            f"{'s' if n_mixed_excluded != 1 else ''} at deletion-majority "
            "coordinates"
        )
    if gate_n_mixed > 0:
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
                return VerdictRecord(
                    translated=translated,
                    expected_mutations=list(expected_mutations),
                    verdict=VerdictClass.WRONG_AA,
                    verdict_notes=_join(
                        notes,
                        f"expected {exp_wt}{pos}{exp_mt}, "
                        f"observed {obs_wt}{pos}{obs_mt}",
                    ),
                )

    expected_positions = set(expected_parsed.keys())
    observed_positions = set(observed_parsed.keys())

    # All expected mutations must be present with matching MT to proceed.
    missing_expected = [
        (pos, read)
        for _label, pos, read in expected_site_reads(translated, expected_mutations)
        if pos not in observed_parsed
    ]
    if missing_expected:
        # Missing an expected position = not a PASS; treat as WRONG_AA-style failure.
        #
        # The note says what the well read there, in the same shape as the
        # mismatch note above. "missing expected: L187G" alone left the AA column
        # blank and gave the operator no way to tell a well that stayed wild type
        # from one whose consensus had no call at the site.
        phrases: list[str] = []
        for pos, read in missing_expected:
            wt, mt = expected_parsed[pos]
            if read == "WT":
                read = f"WT ({translated.aa_sequence[pos - 1]}{pos})"
            elif read == "no call":
                read = f"no call (X at {pos})"
            elif read == "not covered":
                read = f"not covered ({pos})"
            phrases.append(f"expected {wt}{pos}{mt}, observed {read}")
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.WRONG_AA,
            verdict_notes=_join(notes, "; ".join(phrases)),
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
