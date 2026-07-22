"""8-class verdict classifier.

Priority (fail-first): LOWDEPTH -> INDEL_EVENT (gate -> AMBIGUOUS) -> NO_CALL -> FRAMESHIFT -> MANY -> MIXED -> WRONG_AA -> AMBIGUOUS -> PASS.

Invariant: no verdict counted as reproduced (PASS / AMBIGUOUS, see
``kuma_core.mame.detected``) is returned before the designed mutations have been
matched against the observed ones. The INDEL_EVENT gate therefore only awards
AMBIGUOUS to a well whose designed mutations are already confirmed.
"""

from __future__ import annotations

import re

from kuma_core.mame.models import (
    CompareParams,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)

_AA_SUB_RE = re.compile(r"^([A-Z\*])(\d+)([A-Z\*])$")
_AA_DEL_RE = re.compile(r"^([A-Z\*])(\d+)(del|-)$")
_NT_INDEL_RE = re.compile(r"^(\d+)_INDEL$")


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

    # 2) FRAMESHIFT — two or more nucleotide INDEL markers within `frameshift_window_bp`.
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
        f"{wt}{pos}{mt}" for pos, (wt, mt) in expected_parsed.items() if pos not in observed_parsed
    ]
    if missing_expected:
        # Missing an expected position = not a PASS; treat as WRONG_AA-style failure.
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.WRONG_AA,
            verdict_notes=_join(
                notes, f"missing expected: {', '.join(missing_expected)}"
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
