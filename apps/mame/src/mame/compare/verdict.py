"""6-class verdict classifier.

Priority (fail-first): LOWDEPTH -> FRAMESHIFT -> MANY -> WRONG_AA -> AMBIGUOUS -> PASS.
"""

from __future__ import annotations

import re

from mame.models import (
    CompareParams,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)

_AA_SUB_RE = re.compile(r"^([A-Z\*])(\d+)([A-Z\*])$")
_AA_DEL_RE = re.compile(r"^([A-Z\*])(\d+)(del|-)$")
_NT_INDEL_RE = re.compile(r"^(\d+)_INDEL$")


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

    # 1) LOWDEPTH — file size is the available proxy for depth.
    if translated.barcode.file_size_kb < params.min_file_size_kb:
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
            verdict_notes="consecutive NT indels within frameshift window",
        )

    observed = list(translated.observed_aa_changes)

    # 3) MANY — more observed AA changes than the cutoff.
    if len(observed) > params.many_mutation_cutoff:
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.MANY,
            verdict_notes=f"observed {len(observed)} AA changes > cutoff {params.many_mutation_cutoff}",
        )

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

    # 4) WRONG_AA — expected position hit but MT mismatches.
    for pos, (exp_wt, exp_mt) in expected_parsed.items():
        if pos in observed_parsed:
            obs_wt, obs_mt = observed_parsed[pos]
            if obs_mt != exp_mt:
                return VerdictRecord(
                    translated=translated,
                    expected_mutations=list(expected_mutations),
                    verdict=VerdictClass.WRONG_AA,
                    verdict_notes=(
                        f"expected {exp_wt}{pos}{exp_mt}, observed {obs_wt}{pos}{obs_mt}"
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
            verdict_notes=f"missing expected: {', '.join(missing_expected)}",
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
                    f"{tag} within window(\u00b15 codon of {list(expected_parsed.keys())[0]})"
                    if len(expected_parsed) == 1
                    else f"{tag} within \u00b15 codon of {exp_pos}"
                )
                break
    if window_hits:
        return VerdictRecord(
            translated=translated,
            expected_mutations=list(expected_mutations),
            verdict=VerdictClass.AMBIGUOUS,
            verdict_notes="; ".join(window_hits),
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
            verdict_notes=f"unexpected extra mutations: {', '.join(tags)}",
        )

    # 6) PASS — observed exactly matches expected.
    return VerdictRecord(
        translated=translated,
        expected_mutations=list(expected_mutations),
        verdict=VerdictClass.PASS,
        verdict_notes="",
    )
