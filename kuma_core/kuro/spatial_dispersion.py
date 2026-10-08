"""Opt-in geometry diagnostic for already-mapped, trusted reference C-alpha points.

No parser, homology inference, network, model, UI, or default-selection changes.
The caller establishes one reference/structure frame and one model/chain first.
Finite coordinates alone do NOT establish structural or mapping confidence.

Farthest-first is the standard coverage traversal (Gonzalez, 1985), not a new
biological optimizer or a promise of optimal max-min dispersion. Distances are
Euclidean Angstroms throughout; missing coordinates never become 1-D distances.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
import math
import random
import sys

from kuma_core.kuro.evolvepro import structural_diversity_select

Coordinate = tuple[float, float, float]


@dataclass(frozen=True)
class ResidueIdentity:
    model_id: str
    chain_id: str
    residue_number: int
    insertion_code: str = ""


@dataclass(frozen=True)
class ResiduePoint:
    position: int
    residue_id: ResidueIdentity
    coordinate: Coordinate | None
    score: float


@dataclass(frozen=True)
class SpatialInput:
    frame_id: str
    points: tuple[ResiduePoint, ...]
    eligible: tuple[ResiduePoint, ...]
    excluded: tuple[tuple[int, str], ...]
    duplicate_rows: int


@dataclass(frozen=True)
class DispersionMetrics:
    n_eligible: int
    n_selected: int
    min_pair_distance: float | None
    selected_nearest_neighbor: tuple[tuple[int, float | None], ...]
    candidate_nearest_selected: tuple[tuple[int, float | None], ...]
    coverage_mean: float | None
    coverage_max: float | None
    selected_score_sum: float
    total_score_loss: float
    mean_score_loss: float | None


def _finite_score(score: float) -> float:
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError("score must be a finite number")
    try:
        result = float(score)
    except OverflowError as exc:
        raise ValueError("score is not representable") from exc
    if not math.isfinite(result):
        raise ValueError("score must be finite")
    return result


def prepare_trusted_residues(
    points: Iterable[ResiduePoint], *, frame_id: str,
) -> SpatialInput:
    """Validate a caller-established frame, canonicalize and report exclusions.

    Reference positions are positive integers. One model/chain only. Full author
    residue identity (including insertion code) is retained; author numbers may
    be negative or zero. Exact duplicate rows collapse; conflicting duplicate
    positions or non-injective residue mappings fail. Multiple variant scores
    at a position must be resolved explicitly by the caller, never averaged here.
    Missing/nonfinite C-alpha points are excluded, not assigned synthetic values.
    """
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("a nonempty caller-established frame_id is required")
    by_position: dict[int, tuple[ResiduePoint, str | None]] = {}
    raw_coordinates: dict[int, tuple[str, ...] | None] = {}
    by_residue: dict[ResidueIdentity, int] = {}
    model_chains: set[tuple[str, str]] = set()
    duplicate_rows = 0
    for point in points:
        pos, rid = point.position, point.residue_id
        if type(pos) is not int or pos <= 0:
            raise ValueError("reference position must be a positive integer")
        if (
            not isinstance(rid, ResidueIdentity)
            or not isinstance(rid.model_id, str) or not rid.model_id
            or not isinstance(rid.chain_id, str)
            or type(rid.residue_number) is not int
            or not isinstance(rid.insertion_code, str)
        ):
            raise ValueError("invalid full residue identity")
        model_chains.add((rid.model_id, rid.chain_id))
        if len(model_chains) > 1:
            raise ValueError("only a single model/chain is supported per diagnostic")
        score = _finite_score(point.score)
        reason: str | None = None
        coordinate = point.coordinate
        raw_coordinate: tuple[str, ...] | None = None
        if coordinate is None:
            reason = "missing_ca"
        else:
            if len(coordinate) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) for v in coordinate
            ):
                raise ValueError("coordinate must have three numeric components")
            try:
                coordinate = (float(coordinate[0]), float(coordinate[1]), float(coordinate[2]))
            except OverflowError as exc:
                raise ValueError("coordinate is not representable") from exc
            raw_coordinate = tuple(v.hex() for v in coordinate)
            if not all(math.isfinite(v) for v in coordinate):
                coordinate, reason = None, "nonfinite_ca"
        normalized = (ResiduePoint(pos, rid, coordinate, score), reason)
        if pos in by_position:
            if by_position[pos] != normalized or raw_coordinates[pos] != raw_coordinate:
                raise ValueError(f"conflicting duplicate reference position: {pos}")
            duplicate_rows += 1
            continue
        if rid in by_residue:
            raise ValueError("one structure residue maps to multiple reference positions")
        by_residue[rid] = pos
        by_position[pos] = normalized
        raw_coordinates[pos] = raw_coordinate
    ordered = [by_position[p] for p in sorted(by_position)]
    return SpatialInput(
        frame_id=frame_id,
        points=tuple(p for p, _ in ordered),
        eligible=tuple(p for p, reason in ordered if reason is None),
        excluded=tuple((p.position, reason) for p, reason in ordered if reason is not None),
        duplicate_rows=duplicate_rows,
    )


def _budget(data: SpatialInput, k: int) -> None:
    if type(k) is not int or not 0 <= k <= len(data.eligible):
        raise ValueError("k must be an integer in [0, number of eligible positions]")


def _distance(a: ResiduePoint, b: ResiduePoint) -> float:
    if a.coordinate is None or b.coordinate is None:
        raise ValueError("distance requires two eligible C-alpha coordinates")
    distance = math.dist(a.coordinate, b.coordinate)
    if not math.isfinite(distance):
        raise ValueError("distance exceeds finite numeric range")
    return distance


def select_top_score(data: SpatialInput, k: int) -> tuple[int, ...]:
    """Top score, breaking ties by smallest reference position."""
    _budget(data, k)
    return tuple(p.position for p in sorted(data.eligible, key=lambda p: (-p.score, p.position))[:k])


def select_random(data: SpatialInput, k: int, *, seed: int) -> tuple[int, ...]:
    """Seeded sampling without replacement from canonical position order."""
    _budget(data, k)
    if type(seed) is not int:
        raise ValueError("random seed must be an integer")
    return tuple(random.Random(seed).sample([p.position for p in data.eligible], k))


def select_farthest_first(data: SpatialInput, k: int) -> tuple[int, ...]:
    """Reuse existing full-pool structural selection on single-residue points.

    Seed: highest score then smallest position. Subsequent ties use distance,
    score and canonical position ordering. Every encoded row has ONE point,
    never a multi-residue centroid. Dense internal indices are mapped back to
    preserved reference/residue IDs. Existing defaults are not changed.
    """
    _budget(data, k)
    if k <= 1:
        return select_top_score(data, k)
    points = data.eligible
    known = [p.coordinate for p in points if p.coordinate is not None]
    low = tuple(min(c[axis] for c in known) for axis in range(3))
    high = tuple(max(c[axis] for c in known) for axis in range(3))
    span = math.dist(low, high)
    # The existing selector squares components. Refuse numerically unsafe
    # spans instead of allowing overflow/inf ties to choose arbitrary points.
    if not math.isfinite(span) or span > math.sqrt(sys.float_info.max / 4):
        raise ValueError("coordinate distance span exceeds safe numeric range for existing selector")
    encoded = {p.position: f"A{i}G" for i, p in enumerate(points, 1)}
    decode = {encoded[p.position]: p.position for p in points}
    rows = [(encoded[p.position], p.score) for p in sorted(points, key=lambda p: (-p.score, p.position))]
    coordinates: list[Coordinate | None] = [None] + [p.coordinate for p in points]
    selected, _ = structural_diversity_select(
        rows, k, ca_coords=coordinates, anchor_variants=(), kappa=0.0,
    )
    positions = tuple(decode[row[0]] for row in selected)
    if len(positions) != k or len(set(positions)) != k:
        raise ValueError("existing selector returned incomparable cardinality")
    return positions


def _sum(values: Iterable[float]) -> float:
    numbers = tuple(values)
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError("score/distance sum exceeds finite numeric range")
    try:
        result = math.fsum(numbers)
    except OverflowError:
        # Rare mixed-sign extremes can overflow fsum's intermediate partials
        # even when the final sum is finite. Exact binary-rational fallback is
        # stdlib-only and used only on that exceptional path.
        try:
            result = float(sum((Fraction(v) for v in numbers), Fraction()))
        except OverflowError as exc:
            raise ValueError("score/distance sum exceeds finite numeric range") from exc
    if not math.isfinite(result):
        raise ValueError("score/distance sum exceeds finite numeric range")
    return result


def measure_dispersion(data: SpatialInput, selected_positions: Sequence[int]) -> DispersionMetrics:
    """Separate selected-set separation, candidate coverage and score loss.

    Selected nearest neighbors exclude self; candidate coverage includes selected
    points with distance zero. For k=0 coverage is undefined (None), not infinity.
    For k<2 pair distance and selected nearest neighbors are None. Loss is the
    absolute score-sum difference from top-k on this same eligible universe.
    """
    by_pos = {p.position: p for p in data.eligible}
    if any(type(p) is not int or p not in by_pos for p in selected_positions):
        raise ValueError("selected positions must be eligible reference integers")
    if len(set(selected_positions)) != len(selected_positions):
        raise ValueError("selected positions must be unique")
    positions = sorted(selected_positions)
    selected = [by_pos[p] for p in positions]
    nearest = tuple(
        (p.position, min((_distance(p, q) for q in selected if q.position != p.position), default=None))
        for p in selected
    )
    coverage = tuple(
        (p.position, min((_distance(p, q) for q in selected), default=None))
        for p in data.eligible
    )
    known_nn = [d for _, d in nearest if d is not None]
    known_coverage = [d for _, d in coverage if d is not None]
    score_sum = _sum(p.score for p in selected)
    top_positions = select_top_score(data, len(selected))
    # Ranked top scores dominate ranked selected scores pairwise. Difference
    # first avoids overflowing a top-score total when the actual loss is finite.
    selected_scores = sorted((p.score for p in selected), reverse=True)
    loss = _sum(by_pos[p].score - score for p, score in zip(top_positions, selected_scores))
    return DispersionMetrics(
        n_eligible=len(data.eligible), n_selected=len(selected),
        min_pair_distance=min(known_nn) if known_nn else None,
        selected_nearest_neighbor=nearest,
        candidate_nearest_selected=coverage,
        coverage_mean=_sum(d/len(known_coverage) for d in known_coverage) if known_coverage else None,
        coverage_max=max(known_coverage) if known_coverage else None,
        selected_score_sum=score_sum, total_score_loss=loss,
        mean_score_loss=loss/len(selected) if selected else None,
    )
