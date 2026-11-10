"""Bidirectional conversion between internal and EVOLVEpro variant notation.

Internal notation: 'F89W'  (one-letter AA + position + substitution)
EVOLVEpro notation: '89W'  (position + substitution, no ref AA)

A combination genotype is one clone carrying several substitutions, written as
its components joined by ``:`` or ``/`` ('S304C:V547I'). The lab's EVOLVEpro
files settle which spelling is canonical: ``out/all_rounds_fullform.csv`` holds
``variant`` values in FULL form ('S29I', reference residue included) and the
combination candidate list ``b1_top10_per_order.csv`` writes its tokens as
``S304C:V547I`` with the lab scripts splitting on ``":"``. So the canonical
label of a combination is its full-form components joined by ``":"``, and the
short form of a combination is the per-component short form joined the same way
('304C:547I'), which is what ``out/R2_pooled_activity.csv`` keeps in its
separate ``variant_short`` column beside the full ``variant`` one. Whether the
external EVOLVEpro accepts a short combination is UNVERIFIED, which is why the
full form is the identity here and the short form stays the auxiliary spelling
of the same identity.

v0.3 Phase A-0.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §2-0
"""

from __future__ import annotations

import re

# Module-level constants, single source of truth for both parsers.
_INTERNAL_RE = re.compile(r"^([A-Z])(\d+)([A-Z])$")
_SHORT_RE = re.compile(r"^(\d+)([A-Z])$")

_WT_LITERAL = "WT"

# The separator set ``kuma_core.kuro.mutation.split_multi_notation`` accepts
# (mutation.py:54-66): '/' between mutations and ':' between chains. The rule is
# restated here rather than imported because that function normalises a DESIGN
# REQUEST and this module handles an IDENTITY. It drops ``WT`` tokens and merges
# chains, so it answers 'A2V' for 'A2V:WT', correct for "which primers do I
# design", wrong for "which clone is this", where a stray token means the label
# is not a genotype this path can score. Keeping the rule local also leaves this
# module dependency-free, the way every other notation constant in it is.
_SEPARATOR_RE = re.compile(r"[/:]")
_COMBINATION_SEPARATOR = ":"


def is_canonical_internal(variant: str) -> bool:
    """Return True iff *variant* matches the single-substitution pattern.

    Excludes ``WT`` and multi-substitution strings.
    """
    return _INTERNAL_RE.match(variant) is not None


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
            f"to_evolvepro: cannot parse {internal!r} - expected pattern "
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
            f"from_evolvepro: cannot parse {short!r} - expected pattern "
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


# --------------------------------------------------------------------------
# Combination genotypes
#
# Every function below answers for a single substitution by delegating to the
# single-substitution function above and returning its result or its exception
# verbatim. A label carrying no separator never enters the combination branch,
# so a run of single substitutions produces the same values, the same error
# text and the same exclusion reasons it always did.
# --------------------------------------------------------------------------


def is_combination_label(label: str) -> bool:
    """True iff *label* carries a component separator (``/`` or ``:``).

    Says nothing about whether the components parse; it only routes.
    """
    return _SEPARATOR_RE.search(label) is not None


def _components(label: str) -> list[str]:
    """The component tokens of a combination label, in the order written.

    Raises:
        ValueError: If a token is empty or is not a single substitution. Every
            component must be a substitution: ``WT`` is not dropped here the
            way a design request drops it, because a label states an identity
            and a clone is not partly wild-type.
    """
    tokens = [token.strip() for token in _SEPARATOR_RE.split(label.strip())]
    for token in tokens:
        if _INTERNAL_RE.match(token) is None:
            raise ValueError(
                f"cannot parse combination label {label!r}: component "
                f"{token!r} is not a single substitution (expected pattern "
                "[A-Z]\\d+[A-Z], e.g. 'F89W'); components are separated by "
                "'/' or ':'"
            )
    return tokens


def _sorted_components(label: str) -> list[str]:
    """Components of a combination label in ascending position order.

    The written order is not the identity. The lab writes one genotype three
    ways: ``S304C:V547I`` in the candidate token column, ``V547I_S304C`` in a
    FASTA header and ``V547I;S304C`` in a components column. Ordering by
    position gives the same label for all of them, so a genotype written one
    way is not read as a different clone from the same genotype written the
    other way and then reported as unmapped.

    Raises:
        ValueError: If a component does not parse, or if two components name
            the same position. Two substitutions at one position are not a
            genotype one clone can carry, and the verdict path keys its
            expectations by position (``verdict.py``), where the second would
            silently overwrite the first.
    """
    components = _components(label)
    by_position: dict[int, str] = {}
    for component in components:
        match = _INTERNAL_RE.match(component)
        assert match is not None  # _components validated every token
        position = int(match.group(2))
        if position in by_position:
            raise ValueError(
                f"combination label {label!r} names position {position} twice "
                f"({by_position[position]!r} and {component!r}); one clone "
                "carries one substitution per position"
            )
        by_position[position] = component
    return [by_position[position] for position in sorted(by_position)]


def is_canonical_label(variant: str) -> bool:
    """True iff *variant* is a single substitution or a combination of them.

    Excludes ``WT``, the short form, and any combination whose components do
    not parse or that names one position twice.
    """
    if not is_combination_label(variant):
        return is_canonical_internal(variant)
    try:
        _sorted_components(variant)
    except ValueError:
        return False
    return True


def canonical_label(internal: str) -> str:
    """The canonical spelling of *internal*: components by position, ``:``-joined.

    A single substitution is returned unchanged.

    Raises:
        ValueError: As :func:`_sorted_components`.
    """
    if not is_combination_label(internal):
        return internal
    return _COMBINATION_SEPARATOR.join(_sorted_components(internal))


def to_evolvepro_label(internal: str) -> str:
    """Convert a label to EVOLVEpro short notation, combinations included.

    'F89W' answers '89W' and 'V547I:S304C' answers '304C:547I'. ``WT`` is
    returned unchanged, as in :func:`to_evolvepro`.

    Raises:
        ValueError: From :func:`to_evolvepro` for a malformed single label, or
            from :func:`_sorted_components` for a malformed combination.
    """
    if not is_combination_label(internal):
        return to_evolvepro(internal)
    return _COMBINATION_SEPARATOR.join(
        to_evolvepro(component) for component in _sorted_components(internal)
    )


def is_short_label(short: str) -> bool:
    """True iff *short* is EVOLVEpro short notation, a combination included.

    '89W' and '304C:547I' are; 'F89W', 'WT', '304C:F547I' and a combination
    naming one position twice are not.
    """
    if not is_combination_label(short):
        return _SHORT_RE.match(short) is not None
    try:
        canonical_short_label(short)
    except ValueError:
        return False
    return True


def canonical_short_label(short: str) -> str:
    """The canonical spelling of a short label: components by position, ``:``-joined.

    The short-form counterpart of :func:`canonical_label`, so a sheet naming a
    sample '547I:304C' and a design naming it 'S304C:V547I' answer the same
    key. A single short form is returned unchanged.

    Raises:
        ValueError: If a component is not short notation, or if two components
            name the same position.
    """
    if not is_combination_label(short):
        return short
    tokens = [token.strip() for token in _SEPARATOR_RE.split(short.strip())]
    by_position: dict[int, str] = {}
    for token in tokens:
        match = _SHORT_RE.match(token)
        if match is None:
            raise ValueError(
                f"cannot parse short combination {short!r}: component "
                f"{token!r} is not EVOLVEpro short notation (expected pattern "
                "\\d+[A-Z], e.g. '89W')"
            )
        position = int(match.group(1))
        if position in by_position:
            raise ValueError(
                f"short combination {short!r} names position {position} twice "
                f"({by_position[position]!r} and {token!r}); one clone carries "
                "one substitution per position"
            )
        by_position[position] = token
    return _COMBINATION_SEPARATOR.join(
        by_position[position] for position in sorted(by_position)
    )


def from_evolvepro_label(short: str, ref_seq: str) -> str:
    """Convert EVOLVEpro short notation back to a label, combinations included.

    '304C:547I' answers the canonical full form 'S304C:V547I'. The components
    leave in ascending position order, the order :func:`canonical_label` gives.

    Raises:
        ValueError: As :func:`from_evolvepro`, per component.
    """
    if not is_combination_label(short):
        return from_evolvepro(short, ref_seq)
    tokens = [token.strip() for token in _SEPARATOR_RE.split(short.strip())]
    full = [from_evolvepro(token, ref_seq) for token in tokens]
    return canonical_label(_COMBINATION_SEPARATOR.join(full))
