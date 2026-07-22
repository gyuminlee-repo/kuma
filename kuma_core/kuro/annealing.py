"""Per-enzyme annealing temperature (Ta) recommendation.

Ta is derived from the whole-primer template-annealing Tm of a primer pair,
using the lower of the forward / reverse primer Tm values (the pair anneals no
hotter than its weaker primer). The forward-vs-reverse overlap-region Tm is
never used for Ta.

Sequence source: the whole primer (``forward_seq`` / ``reverse_seq``), not the
non-overlap ``*_binding`` fragment. In partial-overlap mode ``forward_binding``
is only the short 3' extension (7-11 nt), which is non-physical for Ta and out
of the NEB offset model's valid 17-39 nt range; in full-overlap mode it equals
the whole primer. The whole primer is the mode-invariant, in-domain choice and
matches the design's own fwd/rev Tm target (the 62/58 whole-primer targets, not
the 42 overlap target).

Design-time behaviour is untouched: the design Tm scale (62/58/42 targets),
salt parameters, and primer selection all stay as-is. Ta is an additive output
computed from committed, data-driven rules on each profile (``ta_rule`` block in
resources/polymerase_profiles.json). First-source manufacturer rules are
documented in docs/2026-07-16-annealing-ta-rules-verified.md.

The NEB-scale Tm reuses the calibrated path in ``neb_tm`` (no re-derivation).
"""

from __future__ import annotations

from typing import Any

import primer3

from . import neb_tm
from .polymerase import PolymeraseProfile


def wallace_tm(seq: str) -> float:
    """Wallace-rule Tm as used by the Takara PrimeSTAR GXL manual.

    2*(A+T) + 4*(G+C) - 5. The -5 term is the manufacturer offset from the
    classic 2AT+4GC estimate (see the verified-rules doc). GXL only.
    """
    s = seq.upper()
    at = s.count("A") + s.count("T")
    gc = s.count("G") + s.count("C")
    return float(2 * at + 4 * gc - 5)


def raw_wallace_tm(seq: str) -> float:
    """Classic Wallace Tm, 2*(A+T) + 4*(G+C), no offset.

    This is the Thermo DreamTaq manual formula (Tm = 4(G+C) + 2(A+T), no -5).
    Kept distinct from ``wallace_tm`` (Takara GXL, which subtracts 5) so the two
    manufacturers' Wallace variants are never conflated. DreamTaq's Ta then
    applies its own -5 annealing offset via the rule ``delta`` (Ta = Tm - 5).
    """
    s = seq.upper()
    at = s.count("A") + s.count("T")
    gc = s.count("G") + s.count("C")
    return float(2 * at + 4 * gc)


def _primer3_profile_tm(seq: str, profile: PolymeraseProfile) -> float:
    """Nearest-neighbour Tm on this profile's own buffer (read-only).

    Uses the profile's committed salt/method parameters; it does not alter
    them and is decoupled from the design path.
    """
    return primer3.calc_tm(
        seq,
        mv_conc=profile.salt_monovalent,
        dv_conc=profile.salt_divalent,
        dntp_conc=profile.dntp_conc,
        dna_conc=profile.dna_conc,
        tm_method=profile.tm_method,
        salt_corrections_method=profile.salt_correction,
    )


def _neb_tm(seq: str, profile: PolymeraseProfile, neb_offsets: dict[str, Any]) -> float:
    """NEB-scale Tm via the calibrated ``neb_tm`` path.

    Falls back to the profile nearest-neighbour Tm if the profile is not mapped
    to an NEB product (keeps Ta defined rather than raising).
    """
    product = neb_offsets.get("product_map", {}).get(profile.name)
    if product is None:
        product = neb_tm.neb_product_for(profile.name)
    if product is None:
        return _primer3_profile_tm(seq, profile)
    return neb_tm.neb_estimated_tm(seq, product)


# DreamTaq splits by primer length: short primers use the Wallace rule, longer
# ones the nearest-neighbour model. Boundary follows the implementation memo
# (>=25 nt -> NN), which supersedes the ">25" wording in the summary table.
_WALLACE_NN_LEN_CUTOFF = 25


def _wallace_nn_tm(seq: str, profile: PolymeraseProfile) -> float:
    """DreamTaq Tm: raw Wallace (Thermo, no -5) for < cutoff nt, NN for >=.

    Uses ``raw_wallace_tm`` (2AT+4GC), not the GXL ``wallace_tm`` (which bakes
    in -5). The -5 annealing offset for DreamTaq comes from the rule ``delta``.
    """
    if len(seq) >= _WALLACE_NN_LEN_CUTOFF:
        return _primer3_profile_tm(seq, profile)
    return raw_wallace_tm(seq)


def _binding_tm(seq: str, profile: PolymeraseProfile, rule: dict, neb_offsets: dict) -> float:
    """Tm of one binding subsequence on the profile's Ta scale."""
    source = rule["tm_source"]
    if source == "neb_offset":
        return _neb_tm(seq, profile, neb_offsets)
    if source == "primer3_profile":
        return _primer3_profile_tm(seq, profile)
    if source == "wallace_nn":
        return _wallace_nn_tm(seq, profile)
    if source == "wallace":
        return wallace_tm(seq)
    raise ValueError(f"Unknown ta_rule tm_source: {source!r}")


def _empty() -> dict[str, Any]:
    return {
        "recommended_ta": None,
        "ta_mode": None,
        "ta_detail": None,
        "ta_touchdown": None,
    }


def _with_note(detail: str | None, note: str | None) -> str | None:
    if detail is None:
        return None
    if note:
        return f"{detail} [{note}]"
    return detail


def _effective_delta(rule: dict, len_low: int | None) -> float:
    """Ta offset for this rule, honouring an optional short-primer branch.

    NEB Phusion (E0553 section 7 / M0530 section 8): primers longer than 20 nt
    anneal at Tm(low) + 3, but "if the primer length is less than 20
    nucleotides, an annealing temperature equivalent to the Tm of the lower
    primer should be used" (offset 0). The threshold and the short-primer
    offset both live on the profile (``short_primer_len`` /
    ``short_primer_delta``); nothing is hard-coded here.

    ``len_low`` is the length of the primer that set ``tm_low`` (the lower-Tm
    primer), matching the manual wording "the Tm of the lower primer".
    """
    short_len = rule.get("short_primer_len")
    short_delta = rule.get("short_primer_delta")
    if (
        short_len is not None
        and short_delta is not None
        and len_low is not None
        and len_low < short_len
    ):
        return float(short_delta)
    return float(rule["delta"])


def _apply_rule(tm_low: float, rule: dict, len_low: int | None = None) -> dict[str, Any]:
    """Turn the lower binding Tm into the 4-field Ta contract.

    Pure decision logic (no thermodynamics) so boundary behaviour is directly
    testable at exact threshold values. ``len_low`` is the length of the
    lower-Tm primer; it is only consulted by rules that declare a
    short-primer branch, so callers without a length keep the previous
    behaviour.
    """
    note = rule.get("note")
    touchdown = rule.get("touchdown")
    mode = rule["mode"]

    if mode == "fixed":
        fr = rule["fixed_rule"]
        ta = fr["high"] if tm_low > fr["threshold"] else fr["low"]
        return {
            "recommended_ta": float(ta),
            "ta_mode": "fixed",
            "ta_detail": _with_note(rule.get("detail_fixed"), note),
            "ta_touchdown": touchdown,
        }

    # 3-step default, with optional 2-step promotion for high-Tm primers.
    #
    # The promotion is compared against whichever quantity the manufacturer
    # states the rule on (``two_step_basis``):
    #   "ta", NEB wording is "primers with annealing temperatures >= 72 C"
    #          (E0553 section 10), so the computed Ta is the probe. Without
    #          this the 3-step branch can emit an annealing temperature above
    #          the 72 C extension step, which is not a runnable program.
    #   "tm", Toyobo KOD One states its threshold on the primer Tm, so the
    #          raw Tm stays the probe. This is the default when unset, which
    #          keeps every profile that does not declare a basis unchanged.
    ta = float(round(tm_low + _effective_delta(rule, len_low)))

    threshold = rule.get("two_step_threshold")
    two_temp = rule.get("two_step_temp")
    probe = ta if rule.get("two_step_basis") == "ta" else tm_low
    if threshold is not None and two_temp is not None and probe >= threshold:
        return {
            "recommended_ta": float(two_temp),
            "ta_mode": "2step",
            "ta_detail": _with_note(rule.get("detail_2step"), note),
            "ta_touchdown": touchdown,
        }

    return {
        "recommended_ta": ta,
        "ta_mode": "3step",
        "ta_detail": _with_note(rule.get("detail_3step"), note),
        "ta_touchdown": touchdown,
    }


def compute_annealing(
    forward_seq: str,
    reverse_seq: str,
    profile: PolymeraseProfile,
    neb_offsets: dict[str, Any],
) -> dict[str, Any]:
    """Recommend an annealing temperature for a primer pair.

    ``forward_seq`` / ``reverse_seq`` are the whole primer sequences (see the
    module docstring on why the non-overlap fragment is not used).

    Returns the 4-field contract read by the frontend:
    ``recommended_ta`` (float|None), ``ta_mode`` ("3step"|"2step"|"fixed"|None),
    ``ta_detail`` (str|None), ``ta_touchdown`` (str|None).

    Returns all-None when the profile carries no ``ta_rule`` (e.g. custom
    profiles) or when a primer sequence is empty.
    """
    rule = getattr(profile, "ta_rule", None)
    if not rule:
        return _empty()
    if not forward_seq or not reverse_seq:
        return _empty()

    tm_fwd = _binding_tm(forward_seq, profile, rule, neb_offsets)
    tm_rev = _binding_tm(reverse_seq, profile, rule, neb_offsets)
    if tm_fwd <= tm_rev:
        tm_low, len_low = tm_fwd, len(forward_seq)
    else:
        tm_low, len_low = tm_rev, len(reverse_seq)
    return _apply_rule(tm_low, rule, len_low)
