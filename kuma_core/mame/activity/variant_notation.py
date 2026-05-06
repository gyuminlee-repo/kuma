"""Bidirectional conversion between internal and EVOLVEpro variant notation.

Internal notation: 'F89W'  (one-letter AA + position + substitution)
EVOLVEpro notation: '89W'  (position + substitution, no ref AA)

v0.3 Phase A-0.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §2-0
"""

from __future__ import annotations

import re

# Module-level constants — single source of truth for both parsers.
_INTERNAL_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")
_SHORT_RE = re.compile(r"^(\d+)([A-Z])$")

_WT_LITERAL = "WT"


def to_evolvepro(internal: str) -> str:
    """Convert internal notation 'F89W' to EVOLVEpro short notation '89W'.

    'WT' input is returned unchanged per §11-B WT handling rule.

    Args:
        internal: Variant in internal notation (e.g., 'F89W') or 'WT'.

    Returns:
        EVOLVEpro short notation (e.g., '89W') or 'WT' unchanged.

    Raises:
        ValueError: If *internal* does not match [A-Z]\\d+[A-Z] and is not 'WT'.
    """
    if internal == _WT_LITERAL:
        return internal

    m = _INTERNAL_RE.match(internal)
    if m is None:
        raise ValueError(
            f"to_evolvepro: cannot parse {internal!r} — expected pattern "
            "[A-Z]\\d+[A-Z] (e.g. 'F89W') or 'WT'"
        )
    return f"{m.group(2)}{m.group(3)}"


def from_evolvepro(short: str, ref_seq: str) -> str:
    """Convert EVOLVEpro short notation '89W' to internal notation 'F89W'.

    Uses ref_seq to look up the reference amino acid at position *pos*.

    Args:
        short:   EVOLVEpro variant string (e.g., '89W').
        ref_seq: Wild-type reference amino acid sequence (1-indexed positions).

    Returns:
        Internal notation string (e.g., 'F89W').

    Raises:
        ValueError: If *short* does not match \\d+[A-Z].
        ValueError: If *ref_seq* is empty or not provided.
        ValueError: If *pos* is out of range for *ref_seq*.
    """
    if not ref_seq:
        raise ValueError(
            f"from_evolvepro: ref_seq is empty or None; "
            f"required to resolve reference AA for {short!r}"
        )

    m = _SHORT_RE.match(short)
    if m is None:
        raise ValueError(
            f"from_evolvepro: cannot parse {short!r} — expected pattern "
            "\\d+[A-Z] (e.g. '89W')"
        )

    pos_1based = int(m.group(1))
    substitution = m.group(2)

    if pos_1based < 1 or pos_1based > len(ref_seq):
        raise ValueError(
            f"from_evolvepro: position {pos_1based} is out of range for "
            f"ref_seq of length {len(ref_seq)} (from {short!r})"
        )

    ref_aa = ref_seq[pos_1based - 1]  # 0-indexed access
    return f"{ref_aa}{pos_1based}{substitution}"
