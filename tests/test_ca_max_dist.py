"""Tests for ca_max_dist — exactness and determinism above the old 200 cutoff.

ca_max_dist normalises every 3D Cα distance evolvepro scores with, so a value
that moves between runs moves which variants get picked. It used to call
``random.sample(valid, min(200, len(valid)))`` with no seed, which made it
both non-deterministic and biased low on any chain longer than 200 residues.
These tests pin both properties at sizes on each side of that old cutoff.
"""

from __future__ import annotations

import math
import random

import pytest

from kuma_core.kuro.alphafold import ca_max_dist


Coord = tuple[float, float, float]


def _brute_force_max(points: list[Coord]) -> float:
    """Reference answer: every pair, no pruning, no sampling."""
    best = 0.0
    for i in range(len(points)):
        xi, yi, zi = points[i]
        for j in range(i + 1, len(points)):
            xj, yj, zj = points[j]
            d = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            best = max(best, d)
    return best


def _spiral(n: int, *, far_pair: float) -> list[Coord]:
    """n points on a spiral, plus one antipodal pair *far_pair* apart.

    The two planted points are the only pair at that separation, so the true
    maximum is known without computing anything: every spiral point sits within
    a radius of 10 of the origin, and far_pair is chosen well above 20.
    """
    pts: list[Coord] = []
    for i in range(n - 2):
        t = i * 0.37
        pts.append((10.0 * math.cos(t), 10.0 * math.sin(t), (i % 21) - 10.0))
    half = far_pair / 2.0
    # Planted at an index in the middle so the answer cannot come from the
    # scan order happening to start or end on them.
    pts.insert(len(pts) // 2, (0.0, 0.0, half))
    pts.insert(len(pts) // 2, (0.0, 0.0, -half))
    return pts


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [50, 199, 200, 201, 560, 1200])
def test_ca_max_dist_is_deterministic(n: int) -> None:
    """Repeated calls on identical input return an identical value.

    Includes sizes above 200, which is where the old sampling branch kicked in
    and where a 325-residue structure produced 12 distinct values over 30 runs.
    """
    coords: list[Coord | None] = list(_spiral(n, far_pair=137.5))
    first = ca_max_dist(coords)
    for _ in range(20):
        assert ca_max_dist(coords) == first


def test_ca_max_dist_ignores_global_random_state() -> None:
    """Seeding or churning the global RNG cannot change the answer.

    The old implementation read ``random.sample`` off the module-level
    Mersenne Twister, so anything else in the process that touched it moved
    this number.
    """
    coords: list[Coord | None] = list(_spiral(600, far_pair=201.25))
    random.seed(1)
    a = ca_max_dist(coords)
    random.seed(999)
    for _ in range(50):
        random.random()
    b = ca_max_dist(coords)
    assert a == b


# ---------------------------------------------------------------------------
# Exactness — known-answer fixtures on both sides of the old 200 cutoff
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("n", "far_pair"),
    [
        (40, 61.5),     # below the old cutoff: was already exhaustive
        (200, 88.25),   # exactly at the cutoff
        (201, 94.5),    # one past it: the first size the old code sampled
        (560, 137.5),   # IspS-sized, the case that motivated this fix
        (1500, 250.75),
    ],
)
def test_ca_max_dist_returns_planted_maximum(n: int, far_pair: float) -> None:
    """Returns the planted pair separation, not a sampled underestimate."""
    coords: list[Coord | None] = list(_spiral(n, far_pair=far_pair))
    assert ca_max_dist(coords) == pytest.approx(far_pair, abs=1e-9)


@pytest.mark.parametrize("n", [201, 350, 700])
def test_ca_max_dist_matches_brute_force_on_random_clouds(n: int) -> None:
    """Pruned scan agrees with the unpruned all-pairs scan, bit for bit.

    Random clouds rather than planted fixtures, because the centroid-radius
    bound is what could in principle skip the winning pair and a planted
    outlier is the easiest case for it.
    """
    rng = random.Random(n)
    points: list[Coord] = [
        (rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(-40, 40))
        for _ in range(n)
    ]
    assert ca_max_dist(list(points)) == _brute_force_max(points)


def test_ca_max_dist_matches_brute_force_on_elongated_chain() -> None:
    """Same check on a random-walk chain, which is not centroid-symmetric."""
    rng = random.Random(4242)
    x = y = z = 0.0
    points: list[Coord] = []
    for _ in range(800):
        x += rng.uniform(-1, 1) * 3.8
        y += rng.uniform(-1, 1) * 3.8
        z += rng.uniform(-1, 1) * 3.8
        points.append((x, y, z))
    assert ca_max_dist(list(points)) == _brute_force_max(points)


def test_ca_max_dist_skips_missing_coordinates() -> None:
    """None entries (chain breaks) are dropped, and the rest still answer."""
    coords: list[Coord | None] = [None] * 300
    coords[7] = (0.0, 0.0, -25.0)
    coords[250] = (0.0, 0.0, 25.0)
    assert ca_max_dist(coords) == pytest.approx(50.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Degenerate inputs — the return value is a divisor, so it must never be 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "coords",
    [
        [],
        [None, None, None],
        [(1.0, 2.0, 3.0)],
        [(1.0, 2.0, 3.0), None],
    ],
)
def test_ca_max_dist_fewer_than_two_points_returns_one(coords) -> None:
    assert ca_max_dist(coords) == 1.0


def test_ca_max_dist_all_points_coincident_returns_one() -> None:
    """400 identical coordinates give a true maximum of 0; callers divide."""
    coords: list[Coord | None] = [(5.0, 5.0, 5.0)] * 400
    assert ca_max_dist(coords) == 1.0


def test_ca_max_dist_collinear_points() -> None:
    """Degenerate geometry: centroid radii are exact, pruning must still work."""
    coords: list[Coord | None] = [(float(i), 0.0, 0.0) for i in range(500)]
    assert ca_max_dist(coords) == pytest.approx(499.0, abs=1e-9)
