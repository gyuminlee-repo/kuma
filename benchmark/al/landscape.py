"""Rugged (epistatic) combinatorial fitness landscapes — NK model.

The Track-1 ProteinGym test cannot assess local-minima avoidance: a single-mutant
DMS oracle has independent, fixed per-variant fitness, so there is no epistatic
trap for diversity to escape (see REPORT.md §3.1). This module provides the
landscape the PI's rationale actually targets: an NK model with TUNABLE
ruggedness K, where greedy hill-climbing can get stuck in local optima and broad
exploration helps reach the global optimum.

NK model (Kauffman): a genotype is `n_sites` integer alleles in [0, n_alleles).
Each site i contributes f_i(allele_i, alleles of its K neighbors), with f_i drawn
i.i.d. U[0,1) keyed by the (site, local-context) tuple. Fitness = mean of the n
site contributions. K=0 ⇒ smooth single-peak; larger K ⇒ rugged, many local
optima. This is the standard testbed for exploration-vs-exploitation in directed
evolution.
"""

from __future__ import annotations

import hashlib
import itertools

import numpy as np


class NKLandscape:
    def __init__(self, n_sites: int, n_alleles: int = 4, K: int = 2, seed: int = 0):
        if not 0 <= K <= n_sites - 1:
            raise ValueError(f"K must be in [0, n_sites-1]; got K={K}, n_sites={n_sites}")
        self.n_sites = n_sites
        self.n_alleles = n_alleles
        self.K = K
        self.seed = seed
        rng = np.random.default_rng(seed)
        # neighbor set for each site: itself + K following sites (circular)
        self.neighbors = [
            tuple(sorted({i, *[(i + j) % n_sites for j in range(1, K + 1)]}))
            for i in range(n_sites)
        ]
        # per-site contribution tables, keyed by (site, local-context) via hashing
        self._salt = rng.integers(0, 2**31 - 1)
        self._fmap: dict[tuple[int, ...], float] | None = None

    def _site_fitness(self, site: int, genotype: tuple[int, ...]) -> float:
        ctx = tuple(genotype[j] for j in self.neighbors[site])
        h = hashlib.sha256(f"{self._salt}|{site}|{ctx}".encode()).digest()
        # map first 8 bytes to a float in [0,1)
        return int.from_bytes(h[:8], "big") / 2**64

    def fitness(self, genotype: tuple[int, ...]) -> float:
        if len(genotype) != self.n_sites:
            raise ValueError(f"genotype length {len(genotype)} != n_sites {self.n_sites}")
        return float(np.mean([self._site_fitness(i, genotype) for i in range(self.n_sites)]))

    def all_genotypes(self) -> list[tuple[int, ...]]:
        return list(itertools.product(range(self.n_alleles), repeat=self.n_sites))

    def fitness_map(self) -> dict[tuple[int, ...], float]:
        # cached: the full enumeration is reused across oracle/global_optimum/arms.
        if self._fmap is None:
            self._fmap = {g: self.fitness(g) for g in self.all_genotypes()}
        return self._fmap

    def global_optimum(self) -> tuple[tuple[int, ...], float]:
        fm = self.fitness_map()
        g = max(fm, key=fm.get)
        return g, fm[g]

    def _neighbors_1mut(self, g: tuple[int, ...]):
        for i in range(self.n_sites):
            for a in range(self.n_alleles):
                if a != g[i]:
                    yield (*g[:i], a, *g[i + 1 :])

    def local_optima(self) -> list[tuple[int, ...]]:
        """Genotypes with no single-mutation neighbor of higher fitness."""
        fm = self.fitness_map()
        out = []
        for g, fg in fm.items():
            if all(fm[nb] <= fg for nb in self._neighbors_1mut(g)):
                out.append(g)
        return out

    def ruggedness(self) -> dict:
        """Summary: number of local optima and the global max (diagnostic)."""
        lo = self.local_optima()
        _, gmax = self.global_optimum()
        return {"n_sites": self.n_sites, "n_alleles": self.n_alleles, "K": self.K,
                "n_genotypes": self.n_alleles ** self.n_sites,
                "n_local_optima": len(lo), "global_max": gmax}


def genotype_label(g: tuple[int, ...]) -> str:
    return "".join(str(a) for a in g)


def onehot(g: tuple[int, ...], n_alleles: int) -> np.ndarray:
    v = np.zeros(len(g) * n_alleles, dtype=float)
    for i, a in enumerate(g):
        v[i * n_alleles + a] = 1.0
    return v


def hamming(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    return sum(1 for x, y in zip(a, b, strict=True) if x != y)
