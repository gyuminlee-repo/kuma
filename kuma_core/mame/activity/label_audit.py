"""Well<->mutant label-swap detection against NGS verdict evidence.

Phase 1: detection and classification only. No auto-correction. A well's
observed amino-acid changes (from the Analyze verdict sheet's ``observed_aa``
column) are compared against the plate layout's expected mutation for that
well. Discordant wells are classified into one of five categories; a special
"closed permutation" gate distinguishes a genuine well<->well label swap from
a coincidental match (see ``audit_labels`` docstring).

A combination genotype is one clone carrying several substitutions, so its
well is compared against the SET of substitutions its label names. A partly
introduced combination (some components observed, nothing else) is reported in
the catch-all ``extra_mutation`` rather than in a category of its own.

The reason is that no surface shows ``LabelFinding.category`` to anyone. Two
read it, and counted across the repository that is the whole of it: zero
components render it, one serialiser copies it (``_serialise_label_audit`` in
``python-core/sidecar_mame/handlers/activity.py``, which puts it in the
``label_audit`` member of the activity response), one TypeScript guard checks
it (``isLabelFinding`` in ``src/types/mame/validators.ts``, against a
hand-copied set of these five names), one field gates export and it is
``is_closed_permutation`` rather than this one, zero locale strings name any
category, and zero documents and zero CLI paths ask for an audit at all. The
manifest ``build_evolvepro_input`` writes does not carry the audit, and the
saved completion record holds only an output path and a signature.

A sixth name would therefore change no verdict and reach no screen, yet it
would still travel in the response payload, and that guard rejects a whole
response over one category name it does not know: every run holding such a
well would fail in the GUI with nothing on screen to say why. The guard set
and its mirror in ``validators.unions.test.ts`` are hand-copied and no checker
compares either against this module, so one missed name is how that happens.
The trigger is therefore the first surface that shows ``category`` to an
operator: whoever writes it adds ``partial_genotype`` in that same change, and
in that same change replaces the hand-copied list in ``validators.ts`` and its
mirror in ``validators.unions.test.ts`` with lists read out of the
``category=`` assignments in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from kuma_core.mame.activity.variant_notation import (
    canonical_label,
    is_canonical_label,
    is_combination_label,
)
from kuma_core.mame.activity.verdict_ngs import VerdictRow
from kuma_core.mame.export.well_mapper import well_to_seq

_WT_LITERAL = "WT"
_SEQUENCE_COLLAPSE_THRESHOLD = 20
_PLATE_WELL_COUNT = 96
_POSITION_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class LabelFinding:
    """One well's label-audit outcome (only populated for discordant wells)."""

    well: str
    expected: str
    observed: tuple[str, ...]
    category: str
    verdict: str


@dataclass(frozen=True)
class LabelAudit:
    """Plate-level label-audit result."""

    discordant: tuple[LabelFinding, ...]
    n_checked: int
    n_unevaluable: int
    is_closed_permutation: bool
    cycles: tuple[tuple[str, ...], ...]
    geometry: str | None


def _position(label: str) -> str | None:
    """Extract the numeric position token from a variant label, else None."""
    m = _POSITION_RE.search(label)
    return m.group(1) if m else None


def _expected_components(expected: str) -> tuple[str, ...]:
    """The substitutions *expected* names, as a tuple in position order.

    A single substitution answers itself. A combination genotype is one clone
    carrying several substitutions, so it answers all of them: the observed
    evidence of such a well is a set of substitutions and comparing it against
    the whole label as one string can never match. A label this module cannot
    parse answers itself, which is the comparison it already got.
    """
    if not is_combination_label(expected) or not is_canonical_label(expected):
        return (expected,)
    return tuple(canonical_label(expected).split(":"))


def _find_cycles(candidates: dict[str, str]) -> tuple[tuple[str, ...], ...]:
    """Decompose a well->well bijection into its disjoint cycles."""
    visited: set[str] = set()
    cycles: list[tuple[str, ...]] = []
    for start in candidates:
        if start in visited:
            continue
        cycle: list[str] = []
        node = start
        while node not in cycle:
            cycle.append(node)
            visited.add(node)
            node = candidates[node]
        cycles.append(tuple(cycle))
    return tuple(cycles)


def _classify_geometry(cycles: tuple[tuple[str, ...], ...]) -> str | None:
    """Label the plate geometry of a set of closed-permutation cycles.

    Deliberately coarse (4 buckets, per spec): two_swap / contiguous_shift /
    scattered / global_offset. Uses the column-major well index
    ``(col-1)*8 + row`` (``well_mapper.well_to_seq``) to measure displacement.
    """
    if not cycles:
        return None

    displacements: list[int] = []
    modular_displacements: list[int] = []
    for cycle in cycles:
        idx = [well_to_seq(w) for w in cycle]
        n = len(idx)
        for i in range(n):
            delta = idx[(i + 1) % n] - idx[i]
            displacements.append(delta)
            modular_displacements.append(delta % _PLATE_WELL_COUNT)

    if len(cycles) == 1 and len(cycles[0]) == 2:
        return "two_swap"
    if len(set(modular_displacements)) == 1:
        return "global_offset"
    if all(abs(d) <= 3 for d in displacements):
        return "contiguous_shift"
    return "scattered"


def audit_labels(
    layout: dict[str, str],
    verdict_rows: dict[str, VerdictRow],
    *,
    confident_classes: frozenset[str] = frozenset({"PASS", "WRONG_AA"}),
) -> LabelAudit:
    """Cross-check plate layout expectations against observed NGS evidence.

    Args:
        layout: {well_id: mutant_internal} (e.g. {"G08": "Q426D"}). WT wells
            are excluded from the audit.
        verdict_rows: {well_id: VerdictRow} from
            ``verdict_ngs.parse_verdict_rows``.
        confident_classes: verdict classes trusted enough to audit against.
            A well with no verdict row, or whose verdict falls outside this
            set, is "no evidence" and excluded from judgement
            (``n_unevaluable``).

    Returns:
        LabelAudit. ``discordant`` lists every well whose observed evidence
        disagrees with its expected mutation, each tagged with a category:

        - ``not_introduced``: no observed AA changes (wild type).
        - ``wrong_residue``: same position, different substitution.
        - ``extra_mutation``: expected mutation present plus extra changes,
          or a differing position with no cross-well match.
        - ``sequence_collapse``: more than 20 observed AA changes; excluded
          from judgement entirely (also excluded from ``n_checked``).
        - ``cross_well``: only assigned when the closed-permutation gate
          (below) confirms a genuine well<->well swap.

        A combination genotype is one clone carrying several substitutions, so
        its well is audited against the SET of substitutions its label names
        (``F89W/L70V`` expects both). Concordance is set equality, not one
        observed label equal to the whole label string, which no combination
        could ever satisfy: a correct double mutant used to be reported as
        discordant. A partly introduced genotype (some components observed,
        nothing extra) is reported in the catch-all ``extra_mutation``. A
        category of its own is deferred because no surface shows
        ``LabelFinding.category`` to an operator, so no one can misread it
        today, while the two places that do read it are a serialiser and a
        hand-copied TypeScript guard that rejects an unknown name outright; the
        module docstring records what adding ``partial_genotype`` requires.

        Closed-permutation gate: a well is a *cross-well candidate* when its
        observed labels are exactly another well's own expected set (for a
        single substitution, that is its one observed label matching that
        well's label). Let D be the set of such candidate wells. The gate holds, and
        those wells are labeled ``cross_well``, only when the candidates form
        a closed permutation on D: every well in D is claimed by exactly one
        other well in D and nothing points outside D (equivalently, the
        multiset of matched observed labels across D equals the multiset of
        expected labels across D). If the permutation is not closed, no well
        is promoted to ``cross_well`` and each keeps its non-cross-well
        category. A match to a confirmed well outside the candidate set is
        coincidental rather than a reciprocal swap and remains wrong_residue.
    """
    expected_by_well: dict[str, str] = {
        well: mutant
        for well, mutant in layout.items()
        if mutant.strip().upper() != _WT_LITERAL
    }
    # Every well's expectation as the SET of substitutions it names, which is
    # what the observed evidence of that well is. A single substitution is a
    # set of one, so this is the same comparison it always got.
    components_by_well: dict[str, frozenset[str]] = {
        well: frozenset(_expected_components(expected))
        for well, expected in expected_by_well.items()
    }
    components_to_well: dict[frozenset[str], str] = {}
    for well, components in components_by_well.items():
        components_to_well.setdefault(components, well)

    n_checked = 0
    n_unevaluable = 0
    provisional: dict[str, LabelFinding] = {}
    collapsed: list[LabelFinding] = []

    for well, expected in expected_by_well.items():
        vrow = verdict_rows.get(well)
        if vrow is None or vrow.verdict not in confident_classes:
            n_unevaluable += 1
            continue

        observed = vrow.observed_aa
        if len(observed) > _SEQUENCE_COLLAPSE_THRESHOLD:
            collapsed.append(
                LabelFinding(
                    well=well,
                    expected=expected,
                    observed=observed,
                    category="sequence_collapse",
                    verdict=vrow.verdict,
                )
            )
            continue

        n_checked += 1

        components = components_by_well[well]
        observed_set = set(observed)
        no_duplicates = len(observed_set) == len(observed)

        if observed_set == components and no_duplicates:
            continue  # concordant

        if not observed:
            category = "not_introduced"
        elif components <= observed_set:
            category = "extra_mutation"
        else:
            # A missing component whose position is occupied by something else
            # is the wrong residue at that position. Otherwise the well falls
            # into extra_mutation, which the docstring states is this audit's
            # catch-all: a partly introduced combination genotype lands there
            # too. A category of its own is deferred because no surface shows
            # LabelFinding.category: widening the TypeScript union would change
            # no display and no verdict, since is_closed_permutation alone
            # gates the export. It would not be free, though. The name does
            # travel in the activity response, and the hand-copied guard set in
            # validators.ts rejects the whole response over one name it does
            # not know, so Python and TypeScript have to move together.
            # The first component that renders category adds
            # partial_genotype as an elif above this else, scoped to
            # observed_set being a proper subset of components with no extra
            # component and no substitution at a missing position, and in the
            # same change makes the category mirror in
            # validators.unions.test.ts read the category= assignments here.
            missing_positions = {
                _position(component)
                for component in components - observed_set
            }
            same_position = [
                o for o in observed if _position(o) in missing_positions
            ]
            category = "wrong_residue" if same_position else "extra_mutation"

        provisional[well] = LabelFinding(
            well=well,
            expected=expected,
            observed=observed,
            category=category,
            verdict=vrow.verdict,
        )

    # Cross-well candidate detection: does any observed label of a discordant
    # well exactly match another well's own expected label?
    candidates: dict[str, str] = {}
    for well, finding in provisional.items():
        observed_set = frozenset(finding.observed)
        if not finding.observed or len(observed_set) != len(finding.observed):
            continue
        target = components_to_well.get(observed_set)
        if target is not None and target != well:
            candidates[well] = target

    is_closed_permutation = False
    cycles: tuple[tuple[str, ...], ...] = ()
    geometry: str | None = None

    if candidates:
        d_wells = set(candidates.keys())
        targets = list(candidates.values())
        closed = (
            set(targets) == d_wells
            and len(set(targets)) == len(targets)  # injective -> bijective on D
        )
        if closed:
            is_closed_permutation = True
            cycles = _find_cycles(candidates)
            geometry = _classify_geometry(cycles)
            for well in d_wells:
                old = provisional[well]
                provisional[well] = LabelFinding(
                    well=old.well,
                    expected=old.expected,
                    observed=old.observed,
                    category="cross_well",
                    verdict=old.verdict,
                )

    discordant = tuple(provisional.values()) + tuple(collapsed)

    return LabelAudit(
        discordant=discordant,
        n_checked=n_checked,
        n_unevaluable=n_unevaluable,
        is_closed_permutation=is_closed_permutation,
        cycles=cycles,
        geometry=geometry,
    )
